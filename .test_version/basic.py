import sounddevice as sd
import numpy as np
import sys

# --- KONFIGURACE ---
INPUT_DEV = 1   # UMC404HD
OUTPUT_DEV = 4  # HDMI Onkyo
SAMPLERATE = 96000 
BLOCKSIZE = 4096
COEFF = 0.707

# GLOBÁLNÍ PROMĚNNÉ
mode = "sq"

def callback(indata, outdata, frames, time, status):
    global mode
    if status:
        sys.stderr.write(f"[{status}] ")

    # 1. VSTUP (Behringer)
    L = indata[:, 0].astype(np.float32) / 2147483648.0
    R = indata[:, 1].astype(np.float32) / 2147483648.0
    
    # 2. VÝSTUPNÍ MATICE - VYNUCENO 6 KANÁLŮ (5.1)
    # Indexy: 0:FL, 1:FR, 2:Center, 3:LFE, 4:SL, 5:SR
    out_6ch = np.zeros((frames, 6), dtype=np.float32)
    
    if mode == "sq":
        out_6ch[:, 0] = L
        out_6ch[:, 1] = R
        out_6ch[:, 4] = (L - COEFF * R) * COEFF # Zadní levý
        out_6ch[:, 5] = (R + COEFF * L) * COEFF # Zadní pravý
    
    elif mode == "qs":
        out_6ch[:, 0] = L + 0.414 * R
        out_6ch[:, 1] = R + 0.414 * L
        out_6ch[:, 4] = L - 0.414 * R
        out_6ch[:, 5] = R - 0.414 * L
        
    else: # Stereo
        out_6ch[:, 0] = L
        out_6ch[:, 1] = R

    # 3. PŘEVOD NA INT32 A LIMITER
    out_6ch = np.clip(out_6ch, -1.0, 1.0)
    outdata[:] = (out_6ch * 2147483647.0).astype(np.int32)
    
    # VU Metr
    max_in = np.max(np.abs(L)) * 100
    sys.stdout.write(f"\r REŽIM: {mode.upper():<7} | VSTUP: {max_in:4.1f}% | 5.1 VYNUCENO ")
    sys.stdout.flush()

try:
    print(f"Vynucuji režim 5.1 (6 kanálů) na HDMI...")
    # Změna: channels=(2, 6)
    with sd.Stream(device=(INPUT_DEV, OUTPUT_DEV),
                   samplerate=SAMPLERATE,
                   blocksize=BLOCKSIZE,
                   channels=(2, 6), 
                   dtype='int32', 
                   callback=callback):
        
        print("\n[BĚŽÍ] Pokud Onkyo svítí 5.1, je to správně.")
        while True:
            cmd = input().lower().strip()
            if cmd == 'q': mode = "sq"
            elif cmd == 'x': mode = "qs"
            elif cmd == 's': mode = "stereo"
            elif cmd == 'e': break

except Exception as e:
    print(f"\nCHYBA: {e}")
    print("Pokud to píše 'Invalid number of channels', HDMI vyžaduje 8 kanálů (7.1).")