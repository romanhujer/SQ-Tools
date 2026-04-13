#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
import soundfile as sf
from scipy.signal import hilbert
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
         sf.SoundFile(output_file, mode='w', samplerate=samplerate, channels=2) as outfile:
        
        progress = 0
        for block in infile.blocks(blocksize=block_size):
            if block.shape[1] < 6: continue
            
            fl, fr, c, lfe, sl, sr = block[:,0], block[:,1], block[:,2], block[:,3], block[:,4], block[:,5]

            # Hilbert pro fázové posuny
            sl_90 = np.imag(hilbert(sl))
            sr_90 = np.imag(hilbert(sr))

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
    # Tady si zvol, co chceš vyrobit: 'SQ', 'QS', 'MATRIXH' nebo 'PL2'
    create_matrix_from_6ch('tmp_processing/multichannel.wav', 'tmp_processing/master_sq.wav', mode='MH')