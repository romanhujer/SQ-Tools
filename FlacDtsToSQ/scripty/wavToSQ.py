#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
import soundfile as sf
from scipy.signal import hilbert, lfilter, firwin
import os

# --- KONSTANTY A KOEFICIENTY ---
SQRT1_2 = np.sqrt(0.5)      # 0.707
SQRT3_2 = np.sqrt(3) / 2    # 0.866
HALF    = 0.5               # 0.5

def deg2rad(deg): return deg * (np.pi / 180.0)

# QS (Sansui)
QS_A = np.cos(deg2rad(22.5)) # 0.924
QS_B = np.sin(deg2rad(22.5)) # 0.383

# Matrix H (BBC)
MH_A = np.cos(deg2rad(20.0)) # 0.940
MH_B = np.sin(deg2rad(20.0)) # 0.342

# --- PŘÍPRAVA FILTRU (mimo smyčku) ---
# Vytvoříme Hilbertův transformátor jako FIR filtr (lichý počet koeficientů)
def create_hilbert_filter(num_taps=1021):
    # num_taps musí být liché
    t = np.arange(num_taps) - (num_taps - 1) // 2
    h = np.zeros(num_taps)
    h[t % 2 != 0] = 2 / (np.pi * t[t % 2 != 0])
    h *= np.blackman(num_taps) # Okno pro vyhlazení
    return h


def create_matrix_from_6ch(input_file, output_file, mode='SQ'):
    if not os.path.exists(input_file):
        print(f"Chyba: Soubor {input_file} neexistuje!")
        return

    info = sf.info(input_file)
    samplerate = info.samplerate
    total_frames = info.frames
    block_size = samplerate * 10  
    
    print(f"Režim: {mode} | Zpracovávám {info.duration:.2f} s")

    with sf.SoundFile(input_file) as infile, \
         sf.SoundFile(output_file, mode='w', samplerate=samplerate, channels=2, subtype='PCM_24' ) as outfile:
        
        progress = 0

        # Inicializace filtrů pro levý a pravý surround
        h_filter = create_hilbert_filter(2047) # Čím vyšší FS (192k), tím delší filtr je fajn
        # Stavové proměnné (aby se fáze neroztrhla mezi bloky)
        zi_sl = np.zeros(len(h_filter) - 1)
        zi_sr = np.zeros(len(h_filter) - 1)

        for block in infile.blocks(blocksize=block_size):
            if block.shape[1] < 6: continue
            
            fl, fr, c, lfe, sl, sr = block[:,0], block[:,1], block[:,2], block[:,3], block[:,4], block[:,5]
#            fl, fr,  sl, sr = block[:,0], block[:,1], block[:,2], block[:,3]

            # Hilbert pro fázové posuny
            #sl_90 = np.imag(hilbert(sl))
            #sr_90 = np.imag(hilbert(sr))
            # --- UVNITŘ SMYČKY (místo původního hilberta) ---
            sl_90, zi_sl = lfilter(h_filter, 1.0, sl, zi=zi_sl)
            sr_90, zi_sr = lfilter(h_filter, 1.0, sr, zi=zi_sr)


            # --- MATICOVÉ VÝPOČTY ---
            if mode == 'SQ':
                # CBS SQ Matice
                lt = fl + (c * SQRT1_2) - (sl_90 * SQRT1_2) + (sr * SQRT1_2)
                rt = fr + (c * SQRT1_2) + (sr_90 * SQRT1_2) - (sl * SQRT1_2)

            elif mode == 'QS':
                # Sansui QS Matice (přední 22.5°, zadní 22.5°)
                lt = (fl * QS_A) + (fr * QS_B) + (c * SQRT1_2) - (sl_90 * QS_A) + (sr_90 * QS_B)
                rt = (fr * QS_A) + (fl * QS_B) + (c * SQRT1_2) + (sr_90 * QS_A) - (sl_90 * QS_B)

            elif mode == 'MH':
                # BBC Matrix H
                lt = (fl * MH_A) + (fr * MH_B) + (c * SQRT1_2) - (sl_90 * MH_A) + (sr_90 * MH_B)
                rt = (fr * MH_A) + (fl * MH_B) + (c * SQRT1_2) + (sr_90 * MH_A) - (sl_90 * MH_B)

            elif mode == 'PL2':
                # Dolby Pro Logic II (Surround jsou posunuty o -90° a míchány specificky)
                # Lt = L + 0.707*C - 0.866*SL_90 - 0.5*SR_90
                # Rt = R + 0.707*C + 0.5*SL_90 + 0.866*SR_90
                lt = fl + (c * SQRT1_2) - (sl_90 * SQRT3_2) - (sr_90 * HALF)
                rt = fr + (c * SQRT1_2) + (sl_90 * HALF) + (sr_90 * SQRT3_2)
            
            else:
                print("Neznámý režim!"); return

            # Sestavení sterea a zápis
            stereo_block = np.vstack((lt, rt)).T
            
            # Ochrana proti clippingu (špičková normalizace na blok)
            max_b = np.max(np.abs(stereo_block))
            if max_b > 0.99:
                stereo_block = stereo_block / max_b * 0.95

            outfile.write(stereo_block)
            
            progress += len(block)
            percent = (progress / total_frames) * 100
            print(f"\rPostup: {percent:.1f} %", end='', flush=True)

    print(f"\nHotovo! Režim {mode} uložen.")


if __name__ == "__main__":
    import sys
    
    # Očekáváme: python3 wavToSQ.py <vstup_wav> <vystup_wav> <mode>
    if len(sys.argv) < 4:
        print("Použití: python3 wavToSQ.py vstup.wav vystup.wav MODE")
        sys.exit(1)
        
    in_file = sys.argv[1]
    out_file = sys.argv[2]
    matrix_mode = sys.argv[3] # SQ, QS, PL2 atd.

    create_matrix_from_6ch(in_file, out_file, mode=matrix_mode)
