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

import sounddevice as sd
import numpy as np
from scipy.signal import lfilter
import sys
import os
import select
import time
import subprocess
import argparse

# --- KONFIGURACE ---
VERSION = "1.8.6"

# Nastavíme úvodni indexy 
INPUT_DEV = 'hw:1,0'  # Behringer UMC404HD
OUTPUT_DEV = 'hw:2,3' # Onkyo TX-NR626 

parser = argparse.ArgumentParser()
parser.add_argument('--daemon', action='store_true', help='Běh bez menu na pozadí')
args = parser.parse_args()

IS_DAEMON = args.daemon


# --- PŘEDPOČÍTANÉ KONSTANTY (Globální) ---
# Spočítají se jen jednou při spuštění skriptu

# Pomocná funkce pro převod stupňů na radiány (NumPy pracuje v radiánech)
def deg2rad(deg):
    return deg * (np.pi / 180.0)

# --- NASTAVENÍ ---
REAR_GAIN =  0.5   # 0.25 ~  -6dB ,  0.333 ~ -4.7dB,  0.707 ~ -3dB 

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

FL = 0      # Front L
FR = 1      # Front R
RL = 2      # Rear L - RPi 4 | N150 2
RR = 3      # Real R - RPi 5 | N150 3
FC = 4      # Center - RPi 2 | N150 4
LFE = 5     # Subbwoofer - RPi  3 | N150 5


BLOCKSIZE = 24576  # 16384  # 8192    # Velký buffer pro stabilitu bez Underflow


# --- GLOBÁLNÍ STAV ---
current_sr = 48000
current_dtype = 'int16'
mode = "sq"
enabled_filter = False
threshold = 0.12
gap_size = 3
total_clicks = 0
peak_hold = 0.0
last_status_time = 0
enabled_center = False

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
stream = None


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

#  Experimaental
def de_clicker_pro(data):
    global total_clicks
    if not enabled_filter: return data
    
    rms = np.sqrt(np.mean(data**2))
    dynamic_threshold = threshold + (rms * 0.5) 
    diff = np.diff(data, prepend=data[0])
    click_indices = np.where(np.abs(diff) > dynamic_threshold)[0]
    
    if len(click_indices) > 0:
        last_repaired = -10
        for idx in click_indices:
            if idx <= last_repaired + gap_size: continue
            total_clicks += 1
            start, end = max(0, idx - 1), min(len(data) - 1, idx + gap_size)
            data[start:end] = np.linspace(data[start], data[end], num=end-start)
            last_repaired = idx
    return data


def callback(indata, outdata, frames, time_info, status):
    global state_L, state_R, mode, total_clicks, peak_hold, current_max_in

    if status:
        print(f"ALSA Status: {status}") # Tady uvidíš to 'input underflow'
        pass
    
    # 1. VSTUP (Normalizace)
    shift = 2147483648.0 if current_dtype == 'int32' else 32768.0
    L_raw = indata[:, 0].astype(np.float32) / shift
    R_raw = indata[:, 1].astype(np.float32) / shift

    # 2. DE-CLICKER (pokud je zapnutý)
    L_clean = de_clicker_pro(L_raw) if enabled_filter else L_raw
    R_clean = de_clicker_pro(R_raw) if enabled_filter else R_raw

    # Bypass 4:4 
    if mode == "bypass" :   # Full bypass 4 kanaly pro UMC404
        LS_raw = indata[:, 2].astype(np.float32) / shift
        RS_raw = indata[:, 3].astype(np.float32) / shift
        # DE-CLICKER (pokud je zapnutý)
        LS_clean = de_clicker_pro(LS_raw) if enabled_filter else LS_raw
        RS_clean = de_clicker_pro(RS_raw) if enabled_filter else RS_raw
    else:
        LS_clean = 0
        RS_clean = 0
 
 
    # 3. HILBERT (90°) - Nutné pro SQ i QS
    L_90, state_L = lfilter(h_coeffs, 1.0, L_clean, zi=state_L)
    R_90, state_R = lfilter(h_coeffs, 1.0, R_clean, zi=state_R)

    # 4. MATICE VÝSTUPU (6 kanálů)
    out_6ch = np.zeros((frames, 6), dtype=np.float32)

    # --- MATICE SQ ---
    if mode == "sq":
        out_6ch[:, FL] = L_clean
        out_6ch[:, FR] = R_clean
        out_6ch[:, RL] = (-SQRT1_2 * L_90) + (SQRT1_2 * R_clean)
        out_6ch[:, RR] = (SQRT1_2 * L_clean) - (SQRT1_2 * R_90)
        if enabled_center:
            out_6ch[:, FC] = (L_clean + R_clean) * 0.707  # Cenetr Front

    # --- MATICE QS (Sansui) ---
    elif mode == "qs":
        out_6ch[:, FL] = QS_A * L_clean + QS_B * R_clean
        out_6ch[:, FR] = QS_B * L_clean + QS_A * R_clean
        out_6ch[:, RL] = QS_A * L_90 - QS_B * R_90
        out_6ch[:, RR] = QS_B * L_90 - QS_A * R_90
        if enabled_center:
            out_6ch[:, FC] = (L_clean + R_clean) * SQRT1_2  # Cenetr Front
  
    # --- MATICE STEREO-4 (Dynaquad) ---
    elif mode == "stereo4":
        out_6ch[:, FL] = L_clean
        out_6ch[:, FR] = R_clean
        diff = (L_clean - R_clean) * SQRT1_2
        out_6ch[:, RL] = diff
        out_6ch[:, RR] = -diff  # Diferenční signál v protifázi
        if enabled_center:
            out_6ch[:, FC] = (L_clean + R_clean) * SQRT1_2  # Cenetr Front

    # --- BBC Matrix H (pro rozhlasové vysílání) ---
    elif mode == "matrixh":
        # FL = L*cos(20) + j*R*sin(20) ... atd.
        out_6ch[:, FL] = MH_A * L_clean + MH_B * R_90
        out_6ch[:, FR] = MH_B * L_90 + MH_A * R_clean
        out_6ch[:, RL] = MH_A * L_90 - MH_B * R_clean
        out_6ch[:, RR] = -MH_B * L_clean + MH_A * R_90
        if enabled_center:
            out_6ch[:, FC] = (L_clean + R_clean) * SQRT1_2 # Center Front

    # --- MATICE DOLBY STEREO (DOLBY SURROUND) ---
    elif mode == "dolby":
        out_6ch[:, FL] = L_clean
        out_6ch[:, FR] = R_clean
        # Center: 1/sqrt(2) * (L + R)
        out_6ch[:, FC] = SQRT1_2 * (L_clean + R_clean)  
        # Surround: j*1/sqrt(2)*L - j*1/sqrt(2)*R
        # To je totéž jako posunout (L - R) o +90 stupňů
        surround_signal = SQRT1_2 * (L_90 - R_90)
        out_6ch[:, RL] = surround_signal
        out_6ch[:, RR] = surround_signal

    # --- MATICE DOLBY PRO LOGIC II ---
    elif mode == "pl2":
        out_6ch[:, FL] = L_clean
        out_6ch[:, FR] = R_clean
        out_6ch[:, FC] = (L_clean + R_clean) * SQRT1_2
        out_6ch[:, RL] = (SQRT3_2 * L_90) + (HALF * R_90)
        out_6ch[:, RR] = -((HALF * L_90) + (SQRT3_2 * R_90))

    else: # Stereo or Bypass 
        out_6ch[:, FL] =  L_clean
        out_6ch[:, FR] =  R_clean
        if mode == "bypass" :
            out_6ch[:, RL] =  LS_clean
            out_6ch[:, RR] =  RS_clean

    #  Úprava hlasitosti zandích kanalů pokud neni bypass 
    if mode != "bypass" :
        out_6ch[:, RL] *= REAR_GAIN
        out_6ch[:, RR] *= REAR_GAIN

    # Ochrana a Převod (CLIP JE KLÍČOVÝ)
    out_6ch *= 0.9 # Headroom
    np.clip(out_6ch, -1.0, 1.0, out=out_6ch)
    
    if current_dtype == 'int32':
        outdata[:] = (out_6ch * 2147483000.0).astype(np.int32)
    else:
        outdata[:] = (out_6ch * 32760.0).astype(np.int16)

    # 6. DATA PRO MONITOR (jen uložení do proměnných)
    # current_max_in = np.max(np.abs(L_raw))
    # peak_hold = np.max(np.abs(out_6ch)) # Celkový peak výstupu


def start_engine():
    global stream, current_sr, current_dtype
    
    # 1. TOTÁLNÍ RESET
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

    # 2. POKUS O START S OŠETŘENÍM CHYB
    retry_count = 0
    while retry_count < 3:
        try:
            print(f"--- Pokus o start: {current_sr}Hz / {current_dtype} (Pokus {retry_count+1}) ---")
            stream = sd.Stream(
                device=(INPUT_DEV, OUTPUT_DEV),
                samplerate=current_sr,
                blocksize=BLOCKSIZE,
                dtype=current_dtype,
            #    channels=(2, 6),
                channels=(4, 6),  # DŮLEŽITÉ: 4 vstupy (UMC404), 6 výstupů (HDMI)
                callback=callback,
            #    latency='low'      # Zkus přidat toto pro stabilitu v reálném čase
                latency='high'      # Zkus přidat toto pro stabilitu v reálném čase
            )
            stream.start()
            print(f"--- ENGINE BĚŽÍ: {current_sr}Hz ---")
            break # Povedlo se, vyskočíme z cyklu
        except Exception as e:
            print(f"START SELHAL: {e}")
            retry_count += 1
            time.sleep(2.0) # Počkej déle, než to zkusíš znovu



def print_menu():
    bit_str = "24-bit" if current_dtype == 'int32' else "16-bit"
    c_stat = "ON" if enabled_center else "OFF"
    f_stat = "ON" if enabled_filter else "OFF"
    
    print("\n" + "="*78)
    print(f"  QUAD DSP version {VERSION} | HDMI:{OUTPUT_DEV} | {current_sr}Hz | {bit_str}")
    print("="*78)
    print("  VZORKOVÁNÍ: [1] 44.1k  | [2] 48k   | [3] 96k | [4] 192k")
    print("  ROZLIŠENÍ:  [7] 16-bit | [8] 24-bit")
    print("-" * 78)
    print("  MATICE: [q] SQ (CBS)               | [x] QS (Sansui)")
    print("          [f] Stereo-4 (Dynaquad)    | [h] Matrix H (BBC)")
    print("          [d] Dolby Stereo (Surround)| [p] Dolby ProLogic II")
    print("          [s] Stereo                 | [b] Bypass 4:4")               
    print("-" * 78)
    print(f"  NASTAVENÍ:  [c] CENTER:{c_stat:3}  | [n] FILTR:{f_stat:3} | [r] Reset Clicks | [e] Exit")
    print("="*78)    

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


# --- HLAVNÍ BĚH ---

INPUT_DEV, OUTPUT_DEV = find_audio_devices()
init_hw_mixer()
devices = sd.query_devices()

# --- PŘÍPRAVA PŘED SMYČKOU ---
CMD_FILE = "/tmp/quad_cmd"
STATUS_FILE = "/tmp/quad_status"
last_status_time = 0  # Časovač pro zápis na disk
peak_hold = 0.0
current_max_in = 0.0

# --- START LOGIKY ---
if not IS_DAEMON:
    # V terminálu startujeme rovnou
    start_engine()
    print_menu()


try:
    while True:
        current_time = time.time()
         # 1. ZÁPIS STATUSU (pro Kodi)
        if current_time - last_status_time > 0.5:
            status_msg = "RUN" if stream else "STOP"

            # 1. AKTUALIZACE STATUSU (každých 500ms)
            if current_time - last_status_time > 0.5:
                f_stat = "ON" if enabled_filter else "OFF"
                c_stat = "ON" if enabled_center else "OFF"
                bit_depth = "24b" if current_dtype == 'int32' else "16b"
            
                # Výpis do konzole jen pokud nejsme daemon
                if not IS_DAEMON:
                    sys.stdout.write(f"\r STATUS: [{mode.upper()}] {current_sr//1000}k/{bit_depth} | Filter:{f_stat} | Clicks:{total_clicks} | Center:{c_stat}    ")
                    sys.stdout.flush()
            
                # Zápis pro Kodi (to chceme vždycky)
                try:
                    with open(STATUS_FILE, "w") as f:
                        f.write(f"{status_msg}|{mode.upper()}|{current_sr//1000}k|{bit_depth}|{f_stat}|{c_stat}")
                except Exception:
                    pass 
            last_status_time = current_time

        # 2. KONTROLA SOUBORU (Příkazy z Kodi /tmp/quad_cmd)
        # Tato část funguje v obou režimech
        if os.path.exists(CMD_FILE):
            with open(CMD_FILE, "r") as f:
                content = f.read().strip().lower()
            os.remove(CMD_FILE)
            
            if content == 'dsp:start' or content == 'r':
                if not stream: start_engine()
            elif content == 'dsp:stop':
                stop_engine()
            elif content == 'e':
                break
            elif stream: # Ostatní příkazy (matice atd.) zpracuj jen když běží stream
                # ... tvoje elif cmd == 'q' atd ...
                               
                commands = content.split()
                for cmd in commands:
                    # Logika příkazů (Sampling, Mode atd.)
                    if cmd in ['1', 'sr:44100']: current_sr = 44100; start_engine()
                    elif cmd in ['2', 'sr:48000']: current_sr = 48000; start_engine()
                    elif cmd in ['3', 'sr:96000']: current_sr = 96000; start_engine()
                    elif cmd in ['4', 'sr:192000']: current_sr = 192000; start_engine() 
                    elif cmd in ['7', 'bit:16']: current_dtype = 'int16'; start_engine()
                    elif cmd in ['8', 'bit:24']: current_dtype = 'int32'; start_engine()
                    elif cmd.startswith('mode:'):
                        mode = cmd.split(':')[1]
                        # start_engine() #pokud stream neběží
                    # Režimy matic
                    elif cmd in ['q', 'mode:sq']: mode = "sq"
                    elif cmd in ['x', 'mode:qs']: mode = "qs"
                    elif cmd in ['s', 'mode:stereo']: mode = "stereo"
                    elif cmd in ['d', 'mode:dolby']: mode = "dolby"
                    elif cmd in ['p', 'mode:pl2']: mode = "pl2"
                    elif cmd in ['h', 'mode:matrixh']: mode = "matrixh"
                    elif cmd in ['f', 'mode:stereo4']: mode = "stereo4" 
                    elif cmd in ['b', 'mode:bypass']: mode = "bypass" 
                    # Nastavení
                    elif cmd in ['n', 'toggle:filter']: enabled_filter = not enabled_filter
                    elif cmd in ['c', 'toggle:center']: enabled_center = not enabled_center
                    elif cmd == 'r': total_clicks = 0
                   
                    # elif cmd == 'e': raise KeyboardInterrupt
                 
                if not IS_DAEMON:
                    print_menu()
                pass    

        # 3. KONTROLA KLÁVESNICE - TOTO JE TA ZMĚNA
        # Spustí se POUZE v interaktivním režimu (--terminal)
        if not IS_DAEMON:
            # select s timeoutem 0 neblokuje, jen se koukne jestli někdo něco zmáčkl
            r, _, _ = select.select([sys.stdin], [], [], 0)
            if r:
                line = sys.stdin.readline().strip().lower()
                if line:
                    if line == 'r': # Manuální restart/start
                        if not stream: start_engine()
                    elif line == 'dsp:stop':
                        stop_engine()
                    elif line == 'q': mode = "sq"
                    elif line == 'x': mode = "qs"
                    elif line == 's': mode = "stereo"
                    elif line == 'd': mode = "dolby"
                    elif line == 'p': mode = "pl2"
                    elif line == 'h': mode = "matrixh"
                    elif line == 'f': mode = "stereo4" 
                    elif line == 'b': mode = "bypass" 
                    elif line == 'n': enabled_filter = not enabled_filter
                    elif line == 'c': enabled_center = not enabled_center
                    elif line == 'r': total_clicks = 0
                    elif line == 'e': break

                    # Sampling z klávesnice
                    elif line in ['1','2','3','4','7','8']:
                        if line == '1': current_sr = 44100
                        elif line == '2': current_sr = 48000
                        elif line == '3': current_sr = 96000
                        elif line == '4': current_sr = 192000
                        elif line == '7': current_dtype = 'int16'
                        elif line == '8': current_dtype = 'int32'
                        start_engine()
                    
                    print_menu()

        # 4. PAUZA
        time.sleep(0.1)

finally:
    stop_engine()
    sys.exit(0)
