#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quadDSP.py - Multi-Matrix Quadraphonic Digital Signal Processor
Location: Jablonec nad Nisou, Czechia (2026)
Author: Roman Hujer

DESCRIPTION:
This processor performs real-time decoding of legacy matrix quadraphonic 
formats (SQ, QS, Matrix H, Dolby Stereo/Surround, PL II) from a 2-channel 
input into a 5.1 LPCM output via HDMI. It utilizes 64-bit floating-point 
precision, Hilbert transform phase-shifting, and high-accuracy 
trigonometric constants for bit-perfect spatial reconstruction.

LICENSE:
Copyright (C) 2026 - Roman Hujer
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""
VERSION = "2.3.1"


import sounddevice as sd
import numpy as np
from scipy.signal import lfilter
import sys, os, select, time, subprocess
import soundfile as sf
from datetime import datetime
import argparse

# --- KONFIGURACE PLATFORMY ---
IS_RPI = os.path.exists('/proc/device-tree/model')
if IS_RPI:
    # RPI 5 Mapování HDMI
    FL, FR, FC, LFE, RL, RR = 0, 1, 2, 3, 4, 5
    platform_name = "Raspberry Pi 5"
#    INPUT_DEV = 'hw:1,0'  # Behringer UMC404HD
#    OUTPUT_DEV = 'hw:2,4' # Onkyo TX-NR626 

else:
    # Intel N150 Mapování HDNI
    FL, FR, RL, RR, FC, LFE = 0, 1, 2, 3, 4, 5
    platform_name = "Intel N150"
#    Nastavíme úvodni indexy 
#    INPUT_DEV = 'hw:1,0'  # Behringer UMC404HD
#    OUTPUT_DEV = 'hw:2,3' # Onkyo TX-NR626 

parser = argparse.ArgumentParser()
parser.add_argument('--daemon', action='store_true', help='Běh bez menu na pozadí')
args = parser.parse_args()

IS_DAEMON = args.daemon

# --- NASTAVENÍ ---
REAR_GAIN =  0.5   # 0.25 ~  -6dB ,  0.333 ~ -4.7dB,  0.707 ~ -3dB 
INPUT_DEV = 'hw:1,0'   # Behringer
OUTPUT_DEV = 'hw:2,3'  # HDMI
REC_PATH = "/storage/recordings"
BLOCKSIZE = 16384
CMD_FILE = "/tmp/quad_cmd"
STATUS_FILE = "/tmp/quad_status"

# Vytvoření složky pro nahrávky, pokud neexistuje
if not os.path.exists(REC_PATH):
    try:
        os.makedirs(REC_PATH)
    except:
        pass

# --- PŘEDPOČÍTANÉ KONSTANTY (Globální) ---
# Spočítají se jen jednou při spuštění skriptu

# Pomocná funkce pro převod stupňů na radiány (NumPy pracuje v radiánech)
def deg2rad(deg): 
    return deg * (np.pi / 180.0)

SQRT1_2 = np.sqrt(0.5)      # 0.707106... (Standard pro SQ, Center, Stereo-4)
SQRT3_2 = np.sqrt(3) / 2    # 0.866025... (Pro Logic II)
HALF    = 0.5               # 0.5         (Pro Logic II, QS)

# QS (Sansui) - Úhel 22.5 stupňů
QS_ANGLE = deg2rad(22.5)
QS_A = np.cos(QS_ANGLE)         # ~0.9239
QS_B = np.sin(QS_ANGLE)         # ~0.3827

# Matrix H (BBC) - Úhel 20 stupňů
MH_ANGLE = deg2rad(20.0)
MH_A = np.cos(MH_ANGLE)         # ~0.9397
MH_B = np.sin(MH_ANGLE)         # ~0.3420

BLOCKSIZE = 24576  # 16384  # 8192    # Velký buffer pro stabilitu bez Underflow

# --- GLOBÁLNÍ STAV ---
current_sr = 48000
current_dtype = 'int32'
active_mode = "decoder" 
matrix_mode = "sq"      

enabled_center = False

is_recording = False
recording_file = None

stream = None
last_status_time = 0


def find_audio_devices():
    import sounddevice as sd
    devices = sd.query_devices()
    in_idx = None
    out_idx = None
    
    print("\n--- SKENOVÁNÍ AUDIO ZAŘÍZENÍ ---")
    for i, dev in enumerate(devices):
        name = dev['name']
        ins = dev['max_input_channels']
        outs = dev['max_output_channels']
        
        # Hledáme Behringer (Vstup) - stačí kousek názvu nebo 'USB Audio' s 4 vstupy
        if ("UMC404" in name.upper() or "BEHRINGER" in name.upper()) and ins >= 2:
            in_idx = i
            print(f"[OK] VSTUP nalezen: Index {i} ({name})")
            
        # Hledáme Onkyo (Výstup)
        if ("TX-NR626" in name.upper() or "HDMI" in name.upper()) and outs >= 6:
            if out_idx is None or "TX-NR626" in name.upper():
                out_idx = i
                print(f"[OK] VÝSTUP nalezen: Index {i} ({name})")

    if in_idx is None or out_idx is None:
        # Pokud stále nic, vypíšeme všechna zařízení pro diagnostiku
        if in_idx is None: print("!!! CHYBA: Nemohu najít VSTUP (Behringer).")
        if out_idx is None: print("!!! CHYBA: Nemohu najít VÝSTUP (Onkyo).")
        sys.exit(1)    
    return in_idx, out_idx



# --- FILTRY (FIR Hilbert 90°) ---
def create_hilbert_fir(n=511):
    if n % 2 == 0: n += 1
    t = np.arange(n) - (n - 1) // 2
    h = np.zeros(n)
    # Hilbertovo jádro
    h[t != 0] = 2 / (np.pi * t[t != 0])
    # Blackmanovo okno pro extrémně nízké zkreslení (vhodné pro 24-bit)
    h *= np.blackman(n)
    return h

# --- INICIALIZACE PŘED STARTEM ---
h_coeffs = create_hilbert_fir(511)
# Inicializace stavů pro hladké navazování bloků (velmi důležité!)
state_L = np.zeros(len(h_coeffs) - 1)
state_R = np.zeros(len(h_coeffs) - 1)

# --- NICIALIZACE MIXÉRU BEHRINGER
def init_hw_mixer():
    print("\n>>> INICIALIZACE MIXÉRU BEHRINGER")
    card = "1"
    # Důležité: 'UMC404HD 192k Output,0' musí být v amixeru v uvozovkách kvůli mezerám
    controls = [
        "Mic,0", 
        "Mic,1", 
        "UMC404HD 192k Output,0", 
        "UMC404HD 192k Output,1"
    ]
    
    for ctrl in controls:
        # Použijeme raději subprocess.run, je bezpečnější než os.system
        cmd = ["amixer", "-c", card, "sset", ctrl, "127", "unmute"]
        print(f"Spouštím: {' '.join(cmd)}")
        try:
            # Tady už nepoužíváme vnitřní uvozovky, subprocess si to ošetří sám
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            print("!!! CHYBA: Příkaz 'amixer' nebyl v kontejneru nalezen. Nainstaluj alsa-utils v Dockerfile.")
        except subprocess.CalledProcessError as e:
            print(f"!!! CHYBA: ALSA odmítla nastavit {ctrl}. (Kód: {e.returncode})")


# --- CALLBACK ---
def callback(indata, outdata, frames, time_info, status):
    global state_L, state_R, matrix_mode, is_recording, recording_file, active_mode
    

    if status:
        print(f"ALSA Status: {status}") # Tady uvidíš to 'input underflow'
        pass
    
    # Ochrana proti IndexError při přepínání režimů
    in_channels = indata.shape[1]

    # VSTUP (Normalizace)
    shift = 2147483648.0 if current_dtype == 'int32' else 32768.0
    
    # MATICE VÝSTUPU (6 kanálů ticho)
    out_6ch = np.zeros((frames, 6), dtype=np.float32)

    try:
        if active_mode == "decoder" and in_channels >= 2:

            L_in = indata[:, 0].astype(np.float32) / shift
            R_in = indata[:, 1].astype(np.float32) / shift
            
            # Bypass 4:4 načtu i zadni kanály
            if matrix_mode == "bypass" :   # Full bypass 4 kanaly pro UMC404
                LS_in = indata[:, 2].astype(np.float32) / shift   
                RS_in = indata[:, 3].astype(np.float32) / shift
            else:
                LS_in = 0
                RS_in = 0

            # HILBERT (90°) - Nutné pro SQ i QS
            L_90, state_L = lfilter(h_coeffs, 1.0, L_in, zi=state_L)
            R_90, state_R = lfilter(h_coeffs, 1.0, R_in, zi=state_R)
            # --- MATICE SQ ---
            if matrix_mode == "sq":
                out_6ch[:, FL] = L_in 
                out_6ch[:, FR] = R_in
                out_6ch[:, RL] = (-SQRT1_2 * L_90) + (SQRT1_2 * R_in)
                out_6ch[:, RR] = (SQRT1_2 * L_in) - (SQRT1_2 * R_90)
           
            # --- MATICE QS (Sansui) ---    
            elif matrix_mode == "qs":
                out_6ch[:, FL] = QS_A * L_in + QS_B * R_in
                out_6ch[:, FR] = QS_B * L_in + QS_A * R_in
                out_6ch[:, RL] = QS_A * L_90 - QS_B * R_90
                out_6ch[:, RR] = QS_B * L_90 - QS_A * R_90

            # --- BBC Matrix H (pro rozhlasové vysílání) ---                
            elif matrix_mode == "matrixh":
                out_6ch[:, FL] = MH_A * L_in + MH_B * R_90
                out_6ch[:, FR] = MH_B * L_90 + MH_A * R_in
                out_6ch[:, RL] = MH_A * L_90 - MH_B * R_in
                out_6ch[:, RR] = -MH_B * L_in + MH_A * R_90
            
             # --- MATICE DOLBY PRO LOGIC II ---    
            elif matrix_mode == "pl2":
                out_6ch[:, FL] = L_in
                out_6ch[:, FR] = R_in
                # Center: 1/sqrt(2) * (L + R)
                # out_6ch[:, FC] = SQRT1_2 * (L_in + R_in)  
                out_6ch[:, RL] = (SQRT3_2 * L_90) + (HALF * R_90)
                out_6ch[:, RR] = -((HALF * L_90) + (SQRT3_2 * R_90))
            
            # --- MATICE DOLBY STEREO (DOLBY SURROUND) ---
            elif matrix_mode == "dolby":
                out_6ch[:, FL] = L_in
                out_6ch[:, FR] = R_in
                # Center: 1/sqrt(2) * (L + R)
                # out_6ch[:, FC] = SQRT1_2 * (L_in + R_in)  
                # Surround: j*1/sqrt(2)*L - j*1/sqrt(2)*R
                # To je totéž jako posunout (L - R) o +90 stupňů
                surround_signal = SQRT1_2 * (L_90 - R_90)
                out_6ch[:, RL] = surround_signal
                out_6ch[:, RR] = surround_signal

            # --- MATICE STEREO-4 (Dynaquad) ---    
            elif matrix_mode == "stereo4":
                out_6ch[:, FL] = L_in
                out_6ch[:, FR] = R_in
                diff = (LS_in - R_in) * SQRT1_2
                out_6ch[:, RL] = diff
                out_6ch[:, RR] = -diff  # Diferenční signál v protifázi
            
            else: # Stereo or Bypass 
                out_6ch[:, FL] =  L_in
                out_6ch[:, FR] =  R_in
                if mode == "bypass" :
                    out_6ch[:, RL] =  LS_in
                    out_6ch[:, RR] =  RS_in

            if enabled_center and matrix_mode not in ["bypass", "stereo"]:
                out_6ch[:, FC] = (L_in + R_in) * SQRT1_2
            
            #  Úprava hlasitosti zandích kanalů pokud neni bypass 
            if matrix_mode != "bypass" :
                out_6ch[:, RL] *=  REAR_GAIN
                out_6ch[:, RR] *=  REAR_GAIN
            
      
        elif active_mode == "encoder" and in_channels >= 4:
            fl = indata[:, 0].astype(np.float32) / shift
            fr = indata[:, 1].astype(np.float32) / shift
            sl = indata[:, 2].astype(np.float32) / shift
            sr = indata[:, 3].astype(np.float32) / shift

            if is_recording and recording_file is not None:
                # Vytvoříme ticho pro 6 kanálů
                rec_data = np.zeros((frames, 6), dtype='float32')
                rec_data[:, 0] = fl  # Front Left
                rec_data[:, 1] = fr  # Front Right
                rec_data[:, 2] = 0   # CENTER (Ticho)
                rec_data[:, 3] = 0   # LFE (Ticho)
                rec_data[:, 4] = sl  # Surround Left
                rec_data[:, 5] = sr  # Surround Right
                recording_file.write(rec_data)
            
            sl_90, state_SL = lfilter(h_coeffs, 1.0, sl, zi=state_SL)
            sr_90, state_SR = lfilter(h_coeffs, 1.0, sr, zi=state_SR)

            if current_mode == 'sq':
                lt = fl - (sl_90 * SQRT1_2) + (sr * SQRT1_2)
                rt = fr + (sr_90 * SQRT1_2) - (sl * SQRT1_2)
            elif current_mode == 'QS':
                lt = (fl * QS_A) + (fr * QS_B) - (sl_90 * QS_A) + (sr_90 * QS_B)
                rt = (fr * QS_A) + (fl * QS_B) + (sr_90 * QS_A) - (sl_90 * QS_B)
            elif current_mode == 'PL2':
                lt = fl - (sl_90 * SQRT3_2) - (sr_90 * HALF)
                rt = fr + (sl_90 * HALF) + (sr_90 * SQRT3_2)

            else:
                 lt = fl
                 rt = fr

            out_final = np.zeros((frames, 4))
            out_final[:, 0] = lt * 0.9
            out_final[:, 1] = rt * 0.9
            if matrix_mode == "bypass": # bypass 4:4 do HDMI 4.0
                out_final[:, 0] = sl * 0.9
                out_final[:, 1] = sr * 0.9
            
            outdata[:] = out_final
                          
    except Exception: 
        pass

    #  Ochrana a Převod (CLIP JE KLÍČOVÝ)
    out_6ch *= 0.9  # Headroom (0.7 - 0.9)
    np.clip(out_6ch, -1.0, 1.0, out=out_6ch)     

    if current_dtype == 'int32':
        outdata[:] = (out_6ch * 2147483000.0).astype(np.int32)
    else:
        outdata[:] = (out_6ch * 32760.0).astype(np.int16)

    # 6. DATA PRO MONITOR (jen uložení do proměnných)
    # current_max_in = np.max(np.abs(L_raw))
    # peak_hold = np.max(np.abs(out_6ch)) # Celkový peak výstupu


# --- ENGINE ---
def start_engine():
    global stream, current_sr, current_dtype
    
    #  TOTÁLNÍ RESET
    if 'stream' in globals() and stream is not None:
        try:
            if stream.active:
                stream.stop()
            stream.close()
        except:
            pass
        stream = None
        # ALSA v LibreELEC potřebuje čas na uvolnění HDMI handshaku
        time.sleep(1.2) 

    #  POKUS O START S OŠETŘENÍM CHYB
    retry_count = 0
    while retry_count < 3:
        try:
            print(f"--- Pokus o start: {current_sr}Hz / {current_dtype} (Pokus {retry_count+1}) ---")
            stream = sd.Stream(
                device=(INPUT_DEV, OUTPUT_DEV),
                samplerate=current_sr,
                blocksize=BLOCKSIZE,
                dtype=current_dtype,
                channels=(4, 6),  # DŮLEŽITÉ: 4 vstupy (UMC404), 6 výstupů (HDMI)
                callback=callback,
            #    latency='low'      # pro stabilitu v reálném čase
                latency='high'     
            )
            stream.start()
            print(f"--- ENGINE BĚŽÍ: {current_sr}Hz ---")
            break # Povedlo se, vyskočíme z cyklu
        except Exception as e:
            print(f"START SELHAL: {e}")
            retry_count += 1
            time.sleep(2.0) # Počkej déle, než to zkusíš znovu

def stop_engine():
    global stream
    if stream is not None:
        try:
            stream.stop()
            stream.close()
            stream = None
            print(">>> Engine uvolnil HDMI (IDLE).")
        except:
            pass



def handle_command(content):
    global active_mode, matrix_mode, is_recording, recording_file, current_sr, current_dtype, enabled_center
    commands = content.split()
    for cmd in commands:
        # Režimy procesoru
        if cmd in ['i', 'decoder:start']: active_mode = "decoder"; start_engine()
        elif cmd in ['l', 'encoder:start']: active_mode = "encoder"; start_engine()
        elif cmd in ['0', 'dsp:stop']: 
            if stream: stream.stop(); stream.close()
        # Vzorkování
        elif cmd in ['1', 'sr:44100']: current_sr = 44100; start_engine()
        elif cmd in ['2', 'sr:48000']: current_sr = 48000; start_engine()
        elif cmd in ['3', 'sr:96000']: current_sr = 96000; start_engine()
        elif cmd in ['4', 'sr:192000']: current_sr = 192000; start_engine()
        # Bitová hloubka
        elif cmd in ['7', 'bit:16']: current_dtype = 'int16'; start_engine()
        elif cmd in ['8', 'bit:24']: current_dtype = 'int32'; start_engine()
        # Matice
        elif cmd in ['q', 'mode:sq']: matrix_mode = "sq"
        elif cmd in ['x', 'mode:qs']: matrix_mode = "qs"
        elif cmd in ['s', 'mode:stereo']: matrix_mode = "stereo"
        elif cmd in ['d', 'mode:dolby']: matrix_mode = "dolby"
        elif cmd in ['p', 'mode:pl2']: matrix_mode = "pl2"
        elif cmd in ['h', 'mode:matrixh']: matrix_mode = "matrixh"
        elif cmd in ['f', 'mode:stereo4']: matrix_mode = "stereo4"
        elif cmd in ['b', 'mode:bypass']: matrix_mode = "bypass"
        # Ostatní
        elif cmd in ['c', 'toggle:center']: enabled_center = not enabled_center
        elif cmd in ['r', 'record:start']:
            if active_mode == "encoder" and not is_recording:
                now = datetime.now().strftime("%Y%m%d-%H%M%S")
                recording_file = sf.SoundFile(os.path.join(REC_PATH, f"{now}.wav"), mode='x', 
                                              samplerate=current_sr, channels=6, subtype='FLOAT')
                is_recording = True
        elif cmd in ['t', 'record:stop']:
            if is_recording: is_recording = False; recording_file.close(); recording_file = None

def print_menu():
    if "--daemon" in sys.argv: return
    bit_str = "24-bit" if current_dtype == 'int32' else "16-bit"
    c_stat = "ON" if enabled_center else "OFF"
    os.system('clear')
    print(f"QUAD DSP v {VERSION} {platform_name}| HDMI:{OUTPUT_DEV} | {current_sr}Hz | {bit_str}")
    print(f"Režim: {active_mode.upper()} | Matice: {matrix_mode.upper()} | Center: {'ON' if enabled_center else 'OFF'}")
    print(f"Záznam: {'NAHRÁVÁ' if is_recording else 'STOP'}")
    print("-" * 78)
    print("[i] Decoder | [l] Encoder |  Record [r] | [t] Stop")
    print("-" * 78)
    print("  VZORKOVÁNÍ: [1] 44.1k  | [2] 48k   | [3] 96k | [4] 192k")
    print("  ROZLIŠENÍ:  [7] 16-bit | [8] 24-bit")
    print("-" * 78)
    print("  MATICE: [q] SQ (CBS)               | [x] QS (Sansui)")
    print("          [f] Stereo-4 (Dynaquad)    | [h] Matrix H (BBC)")
    print("          [d] Dolby Stereo (Surround)| [p] Dolby ProLogic II")
    print("          [s] Stereo                 | [b] Bypass 4:4")               
    print("-" * 78)
    print(f"  NASTAVENÍ:  [c] CENTER:{c_stat:3} | [e] Exit")
    print("Příkaz > ", end='', flush=True)

# --- MAIN ---
INPUT_DEV, OUTPUT_DEV = find_audio_devices()
init_hw_mixer()

start_engine()
if "--daemon" not in sys.argv: print_menu()

try:
    while True:
        if os.path.exists(CMD_FILE):
            with open(CMD_FILE, "r") as f: handle_command(f.read().strip().lower())
            os.remove(CMD_FILE); print_menu()
        
        if "--daemon" not in sys.argv:
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if r:
                line = sys.stdin.readline().strip().lower()
                if line == 'e': break
                handle_command(line); print_menu()
        else:
            time.sleep(1)

        if time.time() - last_status_time > 1.0:
            c_stat = "ON" if enabled_center else "OFF"
            bit_depth = "24b" if current_dtype == 'int32' else "16b"
            with open(STATUS_FILE, "w") as f:
                f.write(f"{'RUN' if stream else 'STOP'}|{matrix_mode.upper()}|{current_sr//1000}k|{bit_depth}|{active_mode.upper()}|{c_stat}")    
            last_status_time = time.time()
finally:
    if recording_file: recording_file.close()
    if stream: stream.stop()

