#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sounddevice as sd
import numpy as np
from scipy.signal import lfilter
import sys
import os
import select
import time
import subprocess
import soundfile as sf
from datetime import datetime

# --- KONFIGURACE PLATFORMY A MAPOVÁNÍ KANÁLŮ ---
IS_RPI = os.path.exists('/proc/device-tree/model')

if IS_RPI:
    # TVŮJ TEST: RASPBERRY PI 5
    FL, FR, FC, LFE, RL, RR = 0, 1, 2, 3, 4, 5
    platform_name = "Raspberry Pi 5 (Zadek na 4/5)"
    # Oprava dle tvého zjištění: RL=4, RR=5, FC=2, LFE=3
    # RL, RR, FC, LFE = 4, 5, 2, 3
else:
    # TVŮJ TEST: INTEL N150
    FL, FR, RL, RR, FC, LFE = 0, 1, 2, 3, 4, 5
    platform_name = "Intel N150 (Zadek na 2/3)"

# --- ZÁKLADNÍ NASTAVENÍ ---
VERSION = "2.2.0-Unified"
INPUT_DEV = 'hw:1,0'   # Behringer UMC404HD
OUTPUT_DEV = 'hw:2,3'  # Onkyo HDMI
REC_PATH = "/storage/recordings"
BLOCKSIZE = 16384
CMD_FILE = "/tmp/quad_cmd"
STATUS_FILE = "/tmp/quad_status"

# --- GLOBÁLNÍ STAV ---
current_sr = 48000
current_dtype = 'int32'
active_mode = "decoder" 
matrix_mode = "sq"      
enabled_filter = False
enabled_center = False
threshold = 0.12        
total_clicks = 0
is_recording = False
recording_file = None
stream = None
last_status_time = 0

# --- MATEMATICKÉ KONSTANTY ---
def deg2rad(deg): return deg * (np.pi / 180.0)
SQRT1_2 = np.sqrt(0.5)
SQRT3_2 = np.sqrt(3) / 2
HALF    = 0.5
QS_A, QS_B = np.cos(deg2rad(22.5)), np.sin(deg2rad(22.5))
MH_A, MH_B = np.cos(deg2rad(20.0)), np.sin(deg2rad(20.0))

# --- HARDWARE A DSP FUNKCE ---
def init_hw_mixer():
    if not IS_RPI: return # Na Intelu může být mixer jinak
    try:
        card = "1"
        controls = ["Mic,0", "Mic,1", "UMC404HD 192k Output,0", "UMC404HD 192k Output,1"]
        for ctrl in controls:
            subprocess.run(["amixer", "-c", card, "sset", ctrl, "127", "unmute"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

def de_clicker_pro(data):
    global total_clicks
    if not enabled_filter: return data
    diff = np.diff(data, prepend=data[0])
    dynamic_threshold = threshold + (np.sqrt(np.mean(data**2)) * 0.5)
    click_indices = np.where(np.abs(diff) > dynamic_threshold)[0]
    for idx in click_indices:
        total_clicks += 1
        start, end = max(0, idx - 1), min(len(data) - 1, idx + 3)
        data[start:end] = np.linspace(data[start], data[end], num=end-start)
    return data

def create_hilbert_fir(n=511):
    if n % 2 == 0: n += 1
    t = np.arange(n) - (n - 1) // 2
    h = np.zeros(n); h[t != 0] = 2 / (np.pi * t[t != 0])
    h *= np.blackman(n)
    return h

h_coeffs = create_hilbert_fir(511)
state_L, state_R = np.zeros(len(h_coeffs)-1), np.zeros(len(h_coeffs)-1)

# --- CALLBACK ---
def callback(indata, outdata, frames, time_info, status):
    global state_L, state_R, matrix_mode, is_recording, recording_file, active_mode, total_clicks
    shift = 2147483648.0 if current_dtype == 'int32' else 32768.0
    out_6ch = np.zeros((frames, 6), dtype=np.float32)

    if active_mode == "decoder":
        L_in = de_clicker_pro(indata[:, 0].astype(np.float32) / shift)
        R_in = de_clicker_pro(indata[:, 1].astype(np.float32) / shift)
        L_90, state_L = lfilter(h_coeffs, 1.0, L_in, zi=state_L)
        R_90, state_R = lfilter(h_coeffs, 1.0, R_in, zi=state_R)

        if matrix_mode == "sq":
            out_6ch[:, FL], out_6ch[:, FR] = L_in, R_in
            out_6ch[:, RL] = (-SQRT1_2 * L_90) + (SQRT1_2 * R_in)
            out_6ch[:, RR] = (SQRT1_2 * L_in) - (SQRT1_2 * R_90)
        elif matrix_mode == "qs":
            out_6ch[:, FL] = QS_A * L_in + QS_B * R_in
            out_6ch[:, FR] = QS_B * L_in + QS_A * R_in
            out_6ch[:, RL] = QS_A * L_90 - QS_B * R_90
            out_6ch[:, RR] = QS_B * L_90 - QS_A * R_90
        elif matrix_mode == "pl2":
            out_6ch[:, FL], out_6ch[:, FR] = L_in, R_in
            out_6ch[:, FC] = (L_in + R_in) * SQRT1_2
            out_6ch[:, RL] = (SQRT3_2 * L_90) + (HALF * R_90)
            out_6ch[:, RR] = -((HALF * L_90) + (SQRT3_2 * R_90))
        
        if enabled_center and matrix_mode != "pl2":
            out_6ch[:, FC] = (L_in + R_in) * SQRT1_2

    else: # ENCODER
        fl, fr, sl, sr = [de_clicker_pro(indata[:, i].astype(np.float32) / shift) for i in range(4)]
        if is_recording and recording_file:
            rec_data = np.zeros((frames, 6), dtype='float32')
            rec_data[:, FL], rec_data[:, FR], rec_data[:, RL], rec_data[:, RR] = fl, fr, sl, sr
            recording_file.write(rec_data)
        
        sl_90, state_L = lfilter(h_coeffs, 1.0, sl, zi=state_L)
        sr_90, state_R = lfilter(h_coeffs, 1.0, sr, zi=state_R)
        
        if matrix_mode == "sq":
            out_6ch[:, FL] = fl - (sl_90 * SQRT1_2) + (sr * SQRT1_2)
            out_6ch[:, FR] = fr + (sr_90 * SQRT1_2) - (sl * SQRT1_2)

    out_6ch *= 0.8
    np.clip(out_6ch, -1.0, 1.0, out=out_6ch)
    if current_dtype == 'int32':
        outdata[:] = (out_6ch * 2147483000.0).astype(np.int32)
    else:
        outdata[:] = (out_6ch * 32760.0).astype(np.int16)

# --- ENGINE CONTROL ---
def start_engine():
    global stream
    if stream: stream.stop(); stream.close(); time.sleep(0.5)
    in_ch = 4 if active_mode == "encoder" else 2
    stream = sd.Stream(device=(INPUT_DEV, OUTPUT_DEV), samplerate=current_sr, 
                       blocksize=BLOCKSIZE, dtype=current_dtype, 
                       channels=(in_ch, 6), callback=callback)
    stream.start()

def handle_command(content):
    global active_mode, matrix_mode, is_recording, recording_file, current_sr, enabled_filter, enabled_center, total_clicks
    for cmd in content.split():
        if cmd in ['i', 'decoder:start']: active_mode = "decoder"; start_engine()
        elif cmd in ['l', 'encoder:start']: active_mode = "encoder"; start_engine()
        elif cmd in ['r', 'record:start'] and active_mode == "encoder":
            if not is_recording:
                now = datetime.now().strftime("%Y%m%d-%H%M%S")
                recording_file = sf.SoundFile(os.path.join(REC_PATH, f"{now}.wav"), mode='x', 
                                              samplerate=current_sr, channels=6, subtype='FLOAT')
                is_recording = True
        elif cmd in ['t', 'record:stop']:
            if is_recording: is_recording = False; recording_file.close(); recording_file = None
        elif cmd in ['q','x','p','h','s']:
            modes = {'q':'sq','x':'qs','p':'pl2','h':'matrixh','s':'stereo'}
            matrix_mode = modes[cmd]
        elif cmd == 'n': enabled_filter = not enabled_filter
        elif cmd == 'c': enabled_center = not enabled_center
        elif cmd == 'reset': total_clicks = 0

def print_menu():
    if "--daemon" in sys.argv: return
    #os.system('clear')
    print(f"QUAD DSP v{VERSION} | Platforma: {platform_name}")
    print(f"Režim: {active_mode.upper()} | Matice: {matrix_mode.upper()} | FS: {current_sr}")
    print(f"Filtr: {'ON' if enabled_filter else 'OFF'} | Center: {'ON' if enabled_center else 'OFF'} | Clicks: {total_clicks}")
    print(f"Záznam: {'NAHRÁVÁ' if is_recording else 'STOP'}")
    print("-" * 60)
    print("[i] Decoder | [l] Encoder | [r/t] Start/Stop Rec")
    print("[q] SQ | [x] QS | [p] PL2 | [h] Matrix H | [s] Stereo")
    print("[n] De-Clicker | [c] Center Mix | [e] Exit")
    print("-" * 60)
    print("Příkaz > ", end='', flush=True)

# --- MAIN LOOP ---
init_hw_mixer()
start_engine()
last_status_time = 0

try:
    if "--daemon" not in sys.argv: print_menu()
    while True:
        # Souborové příkazy
        if os.path.exists(CMD_FILE):
            with open(CMD_FILE, "r") as f: handle_command(f.read().strip().lower())
            os.remove(CMD_FILE)
            print_menu()
        
        # Konzole (jen pokud není daemon)
        if "--daemon" not in sys.argv:
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if r:
                line = sys.stdin.readline().strip().lower()
                if line == 'e': break
                handle_command(line); print_menu()
        else:
            time.sleep(1) # V daemon režimu šetříme CPU

        # Status zápis
        if time.time() - last_status_time > 1.0:
            with open(STATUS_FILE, "w") as f:
                f.write(f"{'RUN' if stream else 'STOP'}|{matrix_mode.upper()}|{active_mode.upper()}|{total_clicks}")
            last_status_time = time.time()
finally:
    if is_recording: recording_file.close()
    if stream: stream.stop()