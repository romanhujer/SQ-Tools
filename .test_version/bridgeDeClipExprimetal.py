import sounddevice as sd
import numpy as np
import sys
import os

# --- ZÁKLADNÍ KONFIGURACE ---
DEFAULT_INPUT = 1       # Index Behringer UMC404HD
DEFAULT_OUTPUT = 4      # Výchozí HDMI
HEADROOM = 0.80         # Rezerva 20% proti ořezu (clippingu)

# --- GLOBÁLNÍ STAV ---
current_sr = 48000
current_dtype = 'int16' # Startujeme na jistotu
mode = "sq"
enabled_filter = False  # Výchozí vypnuto pro čistý poslech
threshold = 0.15        # Citlivost (vysoká = bere jen velké lupance)
gap_size = 4            # Šířka opravy (v počtu vzorků) - NESMÍ BÝT 40!
total_clicks = 0
COEFF = 0.707

stream = None

def init_hw_mixer():
    """Nastaví vstupní citlivost na kartě, aby nebyla ztlumená"""
    print("--- Inicializace HW mixeru (amixer) ---")
    for card in [1, 2]: # Zkusíme obě běžné pozice
        os.system(f"amixer -c {card} sset 'Mic',0 127 > /dev/null 2>&1")
        os.system(f"amixer -c {card} sset 'Mic',1 127 > /dev/null 2>&1")

def find_hdmi_output():
    """Najde správný HDMI port pro Onkyo"""
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        name = dev['name'].lower()
        if 'hdmi' in name and dev['max_output_channels'] >= 6:
            if i in [4, 5]: return i
    return DEFAULT_OUTPUT

def de_clicker_pro(data):
    """Interpoluje lupance (propojí body úsečkou)"""
    global total_clicks
    if not enabled_filter: return data
    
    # Detekce prudké změny (derivace)
    diff = np.diff(data, prepend=data[0])
    click_indices = np.where(np.abs(diff) > threshold)[0]
    
    if len(click_indices) > 0:
        for idx in click_indices:
            total_clicks += 1
            # Krátké okno pro opravu (most)
            start = max(0, idx - 1)
            end = min(len(data) - 1, idx + gap_size)
            # Lineární interpolace (spojnice bodů)
            data[start:end] = np.linspace(data[start], data[end], num=end-start)
    return data

def callback(indata, outdata, frames, time, status):
    global mode, enabled_filter, total_clicks
    if status: sys.stderr.write(f"[{status}] ")

    # 1. Převod na Float + Headroom (ochrana před 'prdáním' u CD)
    shift = 2147483648.0 if current_dtype == 'int32' else 32768.0
    L_raw = (indata[:, 0].astype(np.float32) / shift) * HEADROOM
    R_raw = (indata[:, 1].astype(np.float32) / shift) * HEADROOM
    
    # 2. Filtrace (jen pokud je zapnuto)
    L = de_clicker_pro(L_raw) if enabled_filter else L_raw
    R = de_clicker_pro(R_raw) if enabled_filter else R_raw

    # 3. SQ / QS / Stereo Matice (Výstup 5.1 / 6ch)
    out_6ch = np.zeros((frames, 6), dtype=np.float32)
    if mode == "sq":
        out_6ch[:, 0], out_6ch[:, 1] = L, R
        out_6ch[:, 4] = (L - COEFF * R) * COEFF # Surround L
        out_6ch[:, 5] = (R + COEFF * L) * COEFF # Surround R
    elif mode == "qs":
        out_6ch[:, 0] = L + 0.414 * R
        out_6ch[:, 1] = R + 0.414 * L
        out_6ch[:, 4] = L - 0.414 * R
        out_6ch[:, 5] = R - 0.414 * L
    else: # Stereo
        out_6ch[:, 0], out_6ch[:, 1] = L, R

    # 4. Bezpečný limiter
    out_6ch = np.clip(out_6ch, -0.99, 0.99)
    
    # 5. Výstup zpět do PCM
    if current_dtype == 'int32':
        outdata[:] = (out_6ch * 2147483647.0).astype(np.int32)
    else:
        outdata[:] = (out_6ch * 32767.0).astype(np.int16)

    # Info v terminálu
    peak = np.max(np.abs(out_6ch)) * 100
    f_stat = "ON" if enabled_filter else "OFF"
    sys.stdout.write(f"\r [{mode.upper()}] FILTR:{f_stat} | {current_sr//1000}k/{'24b' if current_dtype=='int32' else '16b'} | PEAK:{peak:4.1f}% | CLICKS:{total_clicks} ")
    sys.stdout.flush()

def start_engine():
    global stream, total_clicks
    if stream: stream.stop(); stream.close()
    total_clicks = 0
    bs = 4096 if current_sr > 48000 else 2048
    print(f"\n>>> ENGINE START: IN:{INPUT_DEV} -> OUT:{OUTPUT_DEV} | {current_sr}Hz | {current_dtype}")
    try:
        stream = sd.Stream(device=(INPUT_DEV, OUTPUT_DEV), samplerate=current_sr,
                           blocksize=bs, channels=(2, 6), dtype=current_dtype, callback=callback)
        stream.start()
    except Exception as e: print(f"\n!!! CHYBA: {e}")

def print_menu():
    bit_info = "24-bit (S32LE)" if current_dtype == 'int32' else "16-bit (S16LE)"
    print("\n" + "="*65)
    print(f"  QUAD DECODER v7.0 | {current_sr}Hz | {bit_info} | HDMI:{OUTPUT_DEV}")
    print("="*65)
    print(" [1] 44.1k | [2] 48k | [3] 96k | [4] 192k")
    print(" [7] 16-bit | [8] 24-bit (pouze pro Behringer/SBX)")
    print(" [q] SQ Režim | [x] QS Režim | [s] Stereo")
    print(" [f] Filtr ON/OFF | [r] Reset počítadla | [e] Konec")
    print("-" * 65)

# --- START PROGRAMU ---
init_hw_mixer()
INPUT_DEV = DEFAULT_INPUT
OUTPUT_DEV = find_hdmi_output()

start_engine()
print_menu()

try:
    while True:
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
    pass
finally:
    if stream: stream.stop(); stream.close()
    