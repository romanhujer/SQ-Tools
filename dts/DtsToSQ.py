#  
#
# Architektura offline konvertoru (DTS 5.1 -> SQ Stereo)
# Abychom z DTS udělali SQ, musíme provést opačný proces než v našem bridge skriptu:
#
# Dekódování DTS: Rozbalit .wav (DTS-CD) na 6 samostatných stop (FL, FR, C, LFE, SL, SR).
#
# SQ Encoding Matrix:
#
# L total =FL+0.707⋅SL−0.707j⋅SR
#
# R Total =FR+0.707⋅SR+0.707j⋅SL
# (Opět tam figuruje ten 90° fázový posun j, aby to SQ dekodér pak správně rozpoznal).


import numpy as np
import soundfile as sf
from scipy.signal import hilbert

def create_sq_from_dts(input_file, output_file):
    # 1. Načtení multikanálového souboru (předpokládáme už rozbalené DTS do WAV)
    data, samplerate = sf.read(input_file)
    
    # Mapování kanálů (standardní 5.1: 0:FL, 1:FR, 2:C, 4:SL, 5:SR)
    fl = data[:, 0]
    fr = data[:, 1]
    sl = data[:, 4]
    sr = data[:, 5]

    # 2. Hilbertova transformace pro 90° posun zadních kanálů
    sl_90 = np.imag(hilbert(sl))
    sr_90 = np.imag(hilbert(sr))

    # 3. SQ Encoding Matice (Standardní CBS SQ parametry)
    # L_total = FL - 0.707 * SL_90 + 0.707 * SR
    # R_total = FR + 0.707 * SR_90 - 0.707 * SL
    lt = fl - (0.707 * sl_90) + (0.707 * sr)
    rt = fr + (0.707 * sr_90) - (0.707 * sl)

    # 4. Normalizace, aby nedošlo k ořezu (clipping) při sčítání
    output = np.vstack((lt, rt)).T
    max_val = np.max(np.abs(output))
    if max_val > 1.0:
        output /= max_val

    # 5. Uložení jako Stereo WAV pro nahrání na pás
    sf.write(output_file, output, samplerate)
    print(f"Hotovo! SQ Stereo uloženo do {output_file}")

# Použití: create_sq_from_dts('multich_file.wav', 'tape_ready_sq.wav')