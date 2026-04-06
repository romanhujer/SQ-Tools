import sounddevice as sd
import numpy as np
from scipy.signal import lfilter
import sys
import os

# --- KONFIGURACE ---
DEFAULT_INPUT = 1   # Behringer UMC404HD
DEFAULT_OUTPUT = 4  # HDMI
BLOCKSIZE = 8192    # Velký buffer pro stabilitu bez Underflow

# --- GLOBÁLNÍ STAV ---
current_sr = 48000
current_dtype = 'int16'
mode = "sq"
enabled_filter = False
threshold = 0.12
gap_size = 3
total_clicks = 0
COEFF_SQ = 0.7071

# --- FILTRY (FIR Hilbert 90°) ---
def create_hilbert_fir(n=127):
    if n % 2 == 0: n += 1
    t = np.arange(n) - (n - 1) // 2
    h = np.zeros(n)
    h[t != 0] = 2 / (np.pi * t[t != 0])
    h *= np.hamming(n)
    return h

h_coeffs = create_hilbert_fir(127)
state_L = np.zeros(len(h_coeffs) - 1)
state_R = np.zeros(len(h_coeffs) - 1)

stream = None

def init_hw_mixer():
    """Nastaví hlasitost na Behringeru"""
    for card in [1, 2]:
        os.system(f"amixer -c {card} sset 'Mic',0 127 > /dev/null 2>&1")
        os.system(f"amixer -c {card} sset 'Mic',1 127 > /dev/null 2>&1")

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

def callback(indata, outdata, frames, time, status):
    global state_L, state_R, mode, total_clicks
    if status: sys.stderr.write(f"[{status}] ")

    # VSTUP
    shift = 2147483648.0 if current_dtype == 'int32' else 32768.0
    L_raw = indata[:, 0].astype(np.float32) / shift
    R_raw = indata[:, 1].astype(np.float32) / shift
    
    # DE-CLICKER
    L_clean = de_clicker_pro(L_raw)
    R_clean = de_clicker_pro(R_raw)

    # HILBERT (Fázový posun 90°)
    L_90, state_L = lfilter(h_coeffs, 1.0, L_clean, zi=state_L)
    R_90, state_R = lfilter(h_coeffs, 1.0, R_clean, zi=state_R)

    # MATICE VÝSTUPU (5.1)
    out_6ch = np.zeros((frames, 6), dtype=np.float32)

    if mode == "sq":
        # CBS SQ Matrix
        out_6ch[:, 0] = L_clean # FL
        out_6ch[:, 1] = R_clean # FR
        out_6ch[:, 4] = (-COEFF_SQ * L_90) + (COEFF_SQ * R_clean) # SL
        out_6ch[:, 5] = (COEFF_SQ * L_clean) - (COEFF_SQ * R_90) # SR

    elif mode == "qs":
        # SANSUI QS Matrix (Full Logic Simulation)
        # FL = L + j*0.414R | FR = R - j*0.414L
        out_6ch[:, 0] = L_clean + (0.414 * R_90)
        out_6ch[:, 1] = R_clean - (0.414 * L_90)
        # SL = L - j*R | SR = R + j*L
        out_6ch[:, 4] = L_clean - R_90
        out_6ch[:, 5] = R_clean + L_90

    else: # Stereo
        out_6ch[:, 0], out_6ch[:, 1] = L_clean, R_clean

    # Ochrana před ořezem (Headroom 0.8)
    out_6ch = np.clip(out_6ch * 0.8, -1.0, 1.0)
    
    if current_dtype == 'int32':
        outdata[:] = (out_6ch * 2147483647.0).astype(np.int32)
    else:
        outdata[:] = (out_6ch * 32767.0).astype(np.int16)

    # Monitor
    max_in = np.max(np.abs(L_raw)) * 100
    f_stat = "FILTR:ON" if enabled_filter else "FILTR:OFF"
    sys.stdout.write(f"\r [{mode.upper()}] {f_stat} | {current_sr//1000}k | In: {max_in:4.1f}% | Clicks: {total_clicks} ")
    sys.stdout.flush()

def start_engine():
    global stream, total_clicks, state_L, state_R
    if stream: stream.stop(); stream.close()
    
    # Reset filtrů při startu nebo změně sample rate
    state_L = np.zeros(len(h_coeffs) - 1)
    state_R = np.zeros(len(h_coeffs) - 1)
    total_clicks = 0
    
    print(f"\n>>> START: {current_sr}Hz | {current_dtype} | Buffer: {BLOCKSIZE}")
    try:
        stream = sd.Stream(device=(INPUT_DEV, OUTPUT_DEV), samplerate=current_sr,
                           blocksize=BLOCKSIZE, channels=(2, 6), dtype=current_dtype, callback=callback)
        stream.start()
    except Exception as e: print(f"\n!!! CHYBA: {e}")

def print_menu():
    bit_str = "24-bit" if current_dtype == 'int32' else "16-bit"
    print("\n" + "="*65)
    print(f"  QUAD PROCESSOR v7.5 | HDMI:{OUTPUT_DEV} | {current_sr}Hz | {bit_str}")
    print("="*65)
    print(" [1] 44.1k | [2] 48k | [3] 96k | [4] 192k")
    print(" [7] 16-bit | [8] 24-bit")
    print(" [q] SQ (CBS) | [x] QS (Sansui) | [s] Stereo")
    print(" [f] Filtr ON/OFF | [r] Reset Clicker | [e] Exit")
    print("-" * 65)

# --- HLAVNÍ BĚH ---
init_hw_mixer()
devices = sd.query_devices()
INPUT_DEV = DEFAULT_INPUT
OUTPUT_DEV = next((i for i, d in enumerate(devices) if 'hdmi' in d['name'].lower() and i in [4, 5]), DEFAULT_OUTPUT)

start_engine()
print_menu()

while True:
    try:
        cmd = input().lower().strip()
        if cmd == '1': current_sr = 44100; start_engine()
        elif cmd == '2': current_sr = 48000; start_engine()
        elif cmd == '3': current_sr = 96000; start_engine()
        elif cmd == '4': current_sr = 192000; start_engine()
        elif cmd == '7': current_dtype = 'int16'; start_engine()
        elif cmd == '8': current_dtype = 'int32'; start_engine()
        elif cmd == 'q': mode = "sq"
        elif cmd == 'x': mode = "qs"
        elif cmd == 's': mode = "stereo"
        elif cmd == 'f': enabled_filter = not enabled_filter
        elif cmd == 'r': total_clicks = 0
        elif cmd == 'e': break
        print_menu()
    except KeyboardInterrupt:
        break

if stream: stream.stop(); stream.close()
