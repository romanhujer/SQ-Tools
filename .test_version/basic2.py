import sounddevice as sd
import numpy as np
import sys

# --- KONFIGURACE HARDWARU (Záložní indexy) ---
DEFAULT_INPUT = 1   # Behringer / USB Audio
DEFAULT_OUTPUT = 4  # HDMI výchozí

# --- AUTOMATICKÝ TEST VÝSTUPU ---
def find_hdmi_output():
    devices = sd.query_devices()
    print("--- SKENOVÁNÍ ZVUKOVÝCH ZAŘÍZENÍ ---")
    found_idx = None
    for i, dev in enumerate(devices):
        name = dev['name'].lower()
        # Hledáme vc4-hdmi, což je standard pro RPi 5
        if 'vc4-hdmi' in name or 'hdmi' in name:
            # Onkyo se obvykle hlásí na zařízení s 6 nebo 8 kanály
            if dev['max_output_channels'] >= 6:
                print(f"[NAPOVĚDA] Nalezeno HDMI na indexu: {i} ({dev['name']})")
                found_idx = i
                # Pokud najdeme index 4 nebo 5, dáváme jim přednost
                if i in [4, 5]:
                    return i
    return found_idx if found_idx is not None else DEFAULT_OUTPUT

# Inicializace zařízení
INPUT_DEV = DEFAULT_INPUT
OUTPUT_DEV = find_hdmi_output()

# --- GLOBÁLNÍ STAV (Tvé parametry) ---
current_sr = 48000
current_dtype = 'int16'
mode = "sq"
enabled_filter = False  # Výchozí vypnuto
threshold = 0.06
total_clicks = 0
COEFF = 0.707

stream = None

def de_clicker(data):
    global total_clicks
    if not enabled_filter:
        return data
    diff = np.diff(data, prepend=0)
    clicks = np.abs(diff) > threshold
    count = np.sum(clicks)
    if count > 0:
        total_clicks += count
        data[clicks] = 0
    return data

def callback(indata, outdata, frames, time, status):
    global mode, enabled_filter, total_clicks
    if status:
        sys.stderr.write(f"[{status}] ")

    if current_dtype == 'int32':
        L_raw = indata[:, 0].astype(np.float32) / 2147483648.0
        R_raw = indata[:, 1].astype(np.float32) / 2147483648.0
    else:
        L_raw = indata[:, 0].astype(np.float32) / 32768.0
        R_raw = indata[:, 1].astype(np.float32) / 32768.0
    
    L = de_clicker(L_raw)
    R = de_clicker(R_raw)

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
    f_status = "[[ FILTER ON ]]" if enabled_filter else "(( FILTER OFF ))"
    sys.stdout.write(f"\r {f_status} | Mode: {mode.upper()} | In: {max_in:4.1f}% | Clicks: {total_clicks}   ")
    sys.stdout.flush()

def start_engine():
    global stream, total_clicks
    if stream:
        stream.stop()
        stream.close()
    
    total_clicks = 0
    bs = 4096 if current_sr > 48000 else 2048
    
    print(f"\n>>> START: IN:{INPUT_DEV} -> OUT:{OUTPUT_DEV} | {current_sr}Hz | {current_dtype}")
    try:
        stream = sd.Stream(device=(INPUT_DEV, OUTPUT_DEV),
                           samplerate=current_sr,
                           blocksize=bs,
                           channels=(2, 6), 
                           dtype=current_dtype, 
                           callback=callback)
        stream.start()
    except Exception as e:
        print(f"\n!!! CHYBA: {e}")

def print_menu():
    print("\n" + "="*65)
    print(f"  QUAD DECODER v5.2 | HDMI Device: {OUTPUT_DEV} | {current_sr}Hz")
    print("="*65)
    print(" [1] 44.1k | [2] 48k | [3] 96k | [4] 192k")
    print(" [7] 16-bit | [8] 24-bit")
    print(" [q] SQ Režim | [x] QS Režim | [s] Stereo")
    print(" [f] Filtr ON/OFF | [r] Reset počítadla | [e] Konec")
    print("-" * 65)

# --- START ---
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
    if stream:
        stream.stop(); stream.close()