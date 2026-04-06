import sounddevice as sd
import numpy as np
import time

INPUT_DEV = 1   # SBX
OUTPUT_DEV = 5  # ONKYO

# Koeficient pro prolnutí fází (SQ standard)
SQ_COEFF = 0.707

def callback(indata, outdata, frames, time_info, status):
    if status:
        print(f"Status: {status}", flush=True)

    # 1. Vstup ze Sound Blasteru (Stereo)
    L = indata[:, 0]
    R = indata[:, 1]

    # 2. SQ Dekódování (Lehká verze bez FFT/Hilbert)
    # Přední kanály
    fl = L
    fr = R
    
    # Zadní kanály (Surround) - fázový mix
    sl = (L - SQ_COEFF * R) * SQ_COEFF
    sr = (R + SQ_COEFF * L) * SQ_COEFF

    # 3. Mapování na 5.0 / 5.1 (HDMI Standard Channel Mapping)
    # Index 0: Front Left
    # Index 1: Front Right
    # Index 2: Center (Ticho)
    # Index 3: LFE / Sub (Ticho)
    # Index 4: Surround Left
    # Index 5: Surround Right
    
    outdata.fill(0) # Vynulování všech kanálů (včetně Centru a LFE)
    
    outdata[:, 0] = fl
    outdata[:, 1] = fr
    outdata[:, 4] = sl
    outdata[:, 5] = sr

    # VU Metr pro vizuální kontrolu všech 4 aktivních kanálů
    avg_level = np.mean(np.abs([fl, fr, sl, sr]))
    print(f"SQ 4.0 -> HDMI 5.0 | Level: {avg_level:.4f}", end='\r', flush=True)

print(f"SPOUŠTÍM SQ DEKODÉR (Layout 5.0)...")

try:
    with sd.Stream(device=(INPUT_DEV, OUTPUT_DEV),
                   samplerate=48000,
                   channels=(2, 6), # Stačí 6 kanálů (L,R,C,LFE,SL,SR)
                   dtype='float32',
                   blocksize=2048,
                   callback=callback):
        while True:
            time.sleep(1)
except Exception as e:
    print(f"\nChyba: {e}")
    