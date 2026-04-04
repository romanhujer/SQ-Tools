import sounddevice as sd
import numpy as np
import sys
import os

# --- KONFIGURACE ---
DEFAULT_INPUT = 1   # UMC404HD
DEFAULT_OUTPUT = 4  # HDMI

# --- GLOBÁLNÍ STAV ---
current_sr = 48000
current_dtype = 'int16'
mode = "sq"
enabled_filter = False
threshold = 0.12     # Zvýšeno pro tvé velké bedny (méně citlivé)
gap_size = 3         # Kolik vzorků se "přemostí" při lupanci
total_clicks = 0
COEFF = 0.707

stream = None

def init_hw_mixer(card_idx=1):
    """Automaticky nastaví hlasitost na Behringeru přes systémové volání"""
    print(f"--- Inicializace mixeru na kartě {card_idx} ---")
    os.system(f"amixer -c {card_idx} sset 'Mic',0 127 > /dev/null 2>&1")
    os.system(f"amixer -c {card_idx} sset 'Mic',1 127 > /dev/null 2>&1")

def de_clicker_pro(data):
    """Inteligentní interpolace s dynamickou bránou (Gate)"""
    global total_clicks
    if not enabled_filter: return data
    
    # 1. ANALÝZA HLASITOSTI (Gate)
    # Spočítáme průměrnou energii v bloku, abychom věděli, jak moc je hudba hlasitá
    rms = np.sqrt(np.mean(data**2))
    # Dynamicky upravíme threshold - v hlasitých pasážích je filtr méně citlivý
    dynamic_threshold = threshold + (rms * 0.5) 

    # 2. DETEKCE ŠPIČEK (Derivace)
    diff = np.diff(data, prepend=data[0])
    abs_diff = np.abs(diff)
    
    # Najdeme indexy, kde změna překročila dynamický práh
    click_indices = np.where(abs_diff > dynamic_threshold)[0]
    
    if len(click_indices) > 0:
        # 3. CHYTRÁ OPRAVA (Interpolace)
        last_repaired = -10 # Ochrana proti překrývání oprav
        
        for idx in click_indices:
            # Pokud je lupanec příliš blízko předchozí opravě, přeskočíme (ochrana dynamiky)
            if idx <= last_repaired + gap_size:
                continue
                
            total_clicks += 1
            # Definujeme okno pro opravu (např. 3-5 vzorků)
            start = max(0, idx - 1)
            end = min(len(data) - 1, idx + gap_size)
            
            # Lineární most mezi čistými vzorky
            data[start:end] = np.linspace(data[start], data[end], num=end-start)
            last_repaired = idx
            
    return data

def de_clicker_proV1(data):
    """Interpoluje lupance místo jejich nulování"""
    global total_clicks
    if not enabled_filter: return data
    
    diff = np.diff(data, prepend=data[0])
    abs_diff = np.abs(diff)
    click_indices = np.where(abs_diff > threshold)[0]
    
    if len(click_indices) > 0:
        total_clicks += len(click_indices)
        for idx in click_indices:
            # Přemostění: vezmeme vzorek před a za lupancem a propojíme je
            start = max(0, idx - 1)
            end = min(len(data) - 1, idx + gap_size)
            data[start:end] = np.linspace(data[start], data[end], num=end-start)
    return data

def callback(indata, outdata, frames, time, status):
    global mode, enabled_filter, total_clicks
    if status: sys.stderr.write(f"[{status}] ")

    # VSTUP
    shift = 2147483648.0 if current_dtype == 'int32' else 32768.0
    L_raw = indata[:, 0].astype(np.float32) / shift
    R_raw = indata[:, 1].astype(np.float32) / shift
    
    # FILTR (Interpolace)
    L = de_clicker_pro(L_raw)
    R = de_clicker_pro(R_raw)

    # MATICE 5.1
    out_6ch = np.zeros((frames, 6), dtype=np.float32)
    if mode == "sq":
        out_6ch[:, 0], out_6ch[:, 1] = L, R
        out_6ch[:, 4] = (L - COEFF * R) * COEFF
        out_6ch[:, 5] = (R + COEFF * L) * COEFF
    elif mode == "qs":
        out_6ch[:, 0] = L + 0.414 * R
        out_6ch[:, 1] = R + 0.414 * L
        out_6ch[:, 4] = L - 0.414 * R
        out_6ch[:, 5] = R - 0.414 * L
    else:
        out_6ch[:, 0], out_6ch[:, 1] = L, R

    out_6ch = np.clip(out_6ch, -1.0, 1.0)
    
    if current_dtype == 'int32':
        outdata[:] = (out_6ch * 2147483647.0).astype(np.int32)
    else:
        outdata[:] = (out_6ch * 32767.0).astype(np.int16)

    max_in = np.max(np.abs(L_raw)) * 100
    f_stat = "FILTR:ON" if enabled_filter else "FILTR:OFF"
    sys.stdout.write(f"\r [{mode.upper()}] {f_stat} | {current_sr//1000}k/{'24b' if current_dtype=='int32' else '16b'} | In: {max_in:4.1f}% | Clicks: {total_clicks} ")
    sys.stdout.flush()

def start_engine():
    global stream, total_clicks
    if stream: stream.stop(); stream.close()
    total_clicks = 0
    bs = 4096 if current_sr > 48000 else 2048
    try:
        stream = sd.Stream(device=(INPUT_DEV, OUTPUT_DEV), samplerate=current_sr,
                           blocksize=bs, channels=(2, 6), dtype=current_dtype, callback=callback)
        stream.start()
    except Exception as e: print(f"\n!!! CHYBA: {e}")

def print_menu():
    bit_str = "24-bit" if current_dtype == 'int32' else "16-bit"
    print("\n" + "="*65)
    print(f"  SQ/QS DECODER v6.0 | HDMI:{OUTPUT_DEV} | {current_sr}Hz | {bit_str}")
    print("="*65)
    print(" [1] 44.1k | [2] 48k | [3] 96k | [4] 192k")
    print(" [7] 16-bit | [8] 24-bit")
    print(" [q] SQ mode | [x] QS mode | [s] Stereo")
    print(" [f] Filtr ON/OFF | [r] Reset Clicker | [e] Exit")
    print("-" * 65)

# --- START ---
# Detekce HDMI
devices = sd.query_devices()
INPUT_DEV = DEFAULT_INPUT
OUTPUT_DEV = next((i for i, d in enumerate(devices) if 'hdmi' in d['name'].lower() and i in [4, 5]), DEFAULT_OUTPUT)

# Nastavení mixeru při startu (zkusíme kartu 1 i 2)
init_hw_mixer(1)
init_hw_mixer(2)

start_engine()
print_menu()

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