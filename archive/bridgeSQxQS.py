import sounddevice as sd
import numpy as np
import time

INPUT_DEV =  1  # 

OUTPUT_DEV = 4  # ONKYO HDMI index for USB Phono Audio 
# OUTPUT_DEV = 5  # ONKYO HDMI index for SoudnBlaster SBX USB card

# Koeficient pro prolnutí fází (SQ standard)
COEFF = 0.707


mode = 1 
modes_desc = ["STEREO (Front Only)", "SQ MATRIX (CBS)", "QS MATRIX (Sansui)"]


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
    sl = (L - COEFF * R) * COEFF
    sr = (R + COEFF * L) * COEFF

    # 3. Mapování na 5.0 / 5.1 (HDMI Standard Channel Mapping)
    # Index 0: Front Left
    # Index 1: Front Right
    # Index 2: Center (Ticho)
    # Index 3: LFE / Sub (Ticho)
    # Index 4: Surround Left
    # Index 5: Surround Right
    
    outdata.fill(0) # Vynulování všech kanálů (včetně Centru a LFE)
    

    if mode == 0: # Stereo
        outdata[:, 0] = L
        outdata[:, 1] = R
    elif mode == 1: # SQ
        outdata[:, 0] = L
        outdata[:, 1] = R
        outdata[:, 4] = (L - COEFF * R) * COEFF
        outdata[:, 5] = (R + COEFF * L) * COEFF
    elif mode == 2: # QS
        outdata[:, 0] = L + 0.414 * R
        outdata[:, 1] = R + 0.414 * L
        outdata[:, 4] = L - 0.414 * R
        outdata[:, 5] = R - 0.414 * L

    # VU Metr pro vizuální kontrolu všech 4 aktivních kanálů
    avg_level = np.mean(np.abs([fl, fr, sl, sr]))
    print(f" AKTIVNÍ: [{modes_desc[mode]}] | Level: {avg_level:.4f}", end='\r', flush=True)

print("--- SQ/QS/Stereo Real-time Decoder ---")
print("Ovládání: Napiš písmeno a potvrď ENTERem:")
print(" s + Enter -> STEREO")
print(" q + Enter -> SQ")
print(" x + Enter -> QS")
print(" e + Enter -> KONEC")

try:
    with sd.Stream(device=(INPUT_DEV, OUTPUT_DEV), samplerate=48000,
                   channels=(2, 6), dtype='float32', callback=callback):
        while True:
            # Standardní input, který v Dockeru funguje spolehlivěji
            cmd = input().strip().lower()
            if cmd == 's': mode = 0
            elif cmd == 'q': mode = 1
            elif cmd == 'x': mode = 2
            elif cmd == 'e': break
            
            print(f"\nPřepnuto na: {modes_desc[mode]}")
except Exception as e:
    print(f"\nChyba: {e}")
