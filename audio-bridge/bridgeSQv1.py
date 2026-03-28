import sounddevice as sd
import numpy as np
from scipy.signal import hilbert
import time

INPUT_DEV = 1   # SBX
OUTPUT_DEV = 5  # ONKYO (8-ch HDMI)

def callback(indata, outdata, frames, time_info, status):
    if status:
        print(status)

    # 1. Získáme L a R ze vstupu
    L = indata[:, 0]
    R = indata[:, 1]

    # 2. Hilbertova transformace pro fázový posun (90 stupňů)
    # Pro SQ potřebujeme imaginární složku (fázově posunutou)
    L_shifted = np.imag(hilbert(L))
    R_shifted = np.imag(hilbert(R))

    # 3. SQ Matice (základní dekódování)
    # Přední kanály (beze změny)
    fl = L
    fr = R
    
    # Zadní kanály (fázová magie)
    # Koeficient 0.707 odpovídá -3dB pro zachování energie
    bl = (-0.707 * L_shifted) + (0.707 * R)
    br = (0.707 * L) - (0.707 * R_shifted)

    # 4. Mapování na 8-kanálový HDMI výstup Onkya
    # Standardní HDMI layout: 0:FL, 1:FR, 2:FC, 3:LFE, 4:BL, 5:BR...
    outdata.fill(0) # Ticho v ostatních kanálech
    outdata[:, 0] = fl  # Front Left
    outdata[:, 1] = fr  # Front Right
    outdata[:, 4] = bl  # Surround Left (Zadní levý)
    outdata[:, 5] = br  # Surround Right (Zadní pravý)

    # VU Metr pro kontrolu aktivity na všech 4 kanálech
    level = np.mean(np.abs([fl, fr, bl, br]))
    print(f"SQ Matrix Active | Quad Level: {level:.4f}", end='\r')

print(f"SQ DEKODÉR: SBX -> ONKYO (4-kanály)")

try:
    with sd.Stream(device=(INPUT_DEV, OUTPUT_DEV),
                   samplerate=48000,
                   channels=(2, 8), # 2 dovnitř, 8 ven (HDMI standard)
                   dtype='float32',
                   blocksize=4096,  # Větší blok kvůli Hilbertově transformaci
                   callback=callback):
        while True:
            time.sleep(1)
except Exception as e:
    print(f"\nChyba: {e}")
    