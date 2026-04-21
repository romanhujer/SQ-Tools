#!/usr/bin/env /Users/hujer/myRec/venv/bin/python3
# -*- coding: utf-8 -*-

##!/usr/bin/env python3
## -*- coding: utf-8 -*-


import numpy as np
import soundfile as sf
from scipy.signal import hilbert
import os


def deg2rad(deg):
    return deg * (np.pi / 180.0)


SQRT1_2 = np.sqrt(0.5)      # 0.707106... (Standard pro SQ, Center, Stereo-4)
SQRT3_2 = np.sqrt(3) / 2    # 0.866025... (Pro Logic II)
HALF    = 0.5               # 0.5         (Pro Logic II, QS)

# QS (Sansui) - Úhel 22.5 stupňů
QS_ANGLE = deg2rad(22.5)
QS_A = np.cos(QS_ANGLE)         # ~0.9239
QS_B = np.sin(QS_ANGLE)         # ~0.3827

# Matrix H (BBC) - Úhel 20 stupňů
MH_ANGLE = deg2rad(20.0)
MH_A = np.cos(MH_ANGLE)         # ~0.9397
MH_B = np.sin(MH_ANGLE)         # ~0.3420


def create_sq_from_6ch_chunked(input_file, output_file):
    if not os.path.exists(input_file):
        print(f"Chyba: Soubor {input_file} neexistuje!")
        return

    # Zjistíme info o souboru bez načítání dat
    info = sf.info(input_file)
    samplerate = info.samplerate
    total_frames = info.frames
    
    # Velikost bloku (např. 10 sekund zvuku)
    block_size = samplerate * 10 
    
    print(f"Zpracovávám {info.duration:.2f} s zvuku po blocích (šetřím RAM)...")

    # Otevřeme vstup a vytvoříme výstup
    with sf.SoundFile(input_file) as infile, \
         sf.SoundFile(output_file, mode='w', samplerate=samplerate, channels=2) as outfile:
        
        progress = 0
        for block in infile.blocks(blocksize=block_size):
            # Block layout: 0:FL, 1:FR, 2:C, 3:LFE, 4:SL, 5:SR
            if block.shape[1] < 6: continue
            
            fl = block[:, 0]
            fr = block[:, 1]
            c  = block[:, 2]
            sl = block[:, 4]
            sr = block[:, 5]

            # Hilbert na malém bloku - tohle už paměť nesežere
            sl_90 = np.imag(hilbert(sl))
            sr_90 = np.imag(hilbert(sr))

            # SQ Matice
            gain_c = SQRT1_2
            gain_sur = SQRT1_2

            lt = fl + (c * gain_c) - (sl_90 * gain_sur) + (sr * gain_sur)
            rt = fr + (c * gain_c) + (sr_90 * gain_sur) - (sl * gain_sur)

            # Sestavení sterea a zápis
            stereo_block = np.vstack((lt, rt)).T
            
            # Mírná ochrana proti clippingu v bloku
            max_b = np.max(np.abs(stereo_block))
            if max_b > 0.99:
                stereo_block = stereo_block / max_b * 0.95

            outfile.write(stereo_block)
            
            progress += len(block)
            percent = (progress / total_frames) * 100
            print(f"\rHotovo: {percent:.1f} %", end='', flush=True)

    print("\n\nVŠE HOTOVO! SQ soubor byl úspěšně vytvořen.")

if __name__ == "__main__":
    create_sq_from_6ch_chunked('tmp_processing/multichannel.wav', 'tmp_processing/master_sq.wav')
