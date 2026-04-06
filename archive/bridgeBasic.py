import sounddevice as sd
import numpy as np
import sys

# INDEXY Z TVÉHO SCANU
INPUT_DEV = 1   # Behringer
OUTPUT_DEV = 4  # HDMI Onkyo

SAMPLERATE = 44100 
BLOCKSIZE = 4096
COEFF = 0.707
mode = 1 

def callback(indata, outdata, frames, time, status):
    if status:
        sys.stderr.write(f"[{status}] ")
    
    # 1. VSTUP (Změněno na 2 kanály)
    # PortAudio by měl automaticky vzít In 1 a In 2 z Behringera
    L = indata[:, 0].astype(np.float32) / 2147483648.0
    R = indata[:, 1].astype(np.float32) / 2147483648.0
    
    # 2. VÝPOČET (SQ) - 8 kanálů pro HDMI
    out_f = np.zeros((frames, 8), dtype=np.float32)
    if mode == 1:
        out_f[:, 0], out_f[:, 1] = L, R
        out_f[:, 4] = (L - COEFF * R) * COEFF # Surround L
        out_f[:, 5] = (R + COEFF * L) * COEFF # Surround R
    else:
        out_f[:, 0], out_f[:, 1] = L, R

    # 3. VÝSTUP (HDMI int32)
    out_f = np.clip(out_f, -1.0, 1.0)
    outdata[:] = (out_f * 2147483647.0).astype(np.int32)
    
    # VU Metr (Procenta)
    max_val = np.max(np.abs(L))
    sys.stdout.write(f"\r IN-L: {max_val*100:4.1f}% | Mode: SQ | Status: OK")
    sys.stdout.flush()

try:
    print(f"Pokus o start: IN:{INPUT_DEV}(2ch) -> OUT:{OUTPUT_DEV}(8ch) @ {SAMPLERATE}Hz")
    
    # KLÍČOVÁ ZMĚNA: channels=(2, 8)
    with sd.Stream(device=(INPUT_DEV, OUTPUT_DEV),
                   samplerate=SAMPLERATE,
                   blocksize=BLOCKSIZE,
                   channels=(2, 8), 
                   dtype='int32', 
                   callback=callback):
        
        print("\n[STREAM BĚŽÍ] Sleduji signál...")
        while True:
            sd.sleep(1000)
            
except Exception as e:
    print(f"\nCHYBA: {e}")
    # Pokud to pořád hází chybu kanálů, vypíšeme co karta 1 skutečně nabízí
    print("\n--- DETEKCE SCHOPNOSTÍ KARTY ---")
    try:
        dev_info = sd.query_devices(INPUT_DEV)
        print(f"Zařízení {INPUT_DEV} ({dev_info['name']}):")
        print(f" Max vstupních kanálů: {dev_info['max_input_channels']}")
    except:
        print("Nelze načíst info o kartě.")