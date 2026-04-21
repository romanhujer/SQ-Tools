#!/usr/bin/env python3
# -*- coding: utf-8 -*-
  
import sounddevice as sd
import numpy as np
from scipy.signal import lfilter
import sys
import time
import select
import os
import soundfile as sf  # Potřeba doinstalovat nebo mít v Dockeru
from datetime import datetime


# --- KONFIGURACE ---
VERSION = "1.2.0-Live-Rec"
BLOCKSIZE = 8192
current_mode = "SQ"
current_fs = 48000
REC_PATH = "/storage/recordings"

# Vytvoření složky pro nahrávky, pokud neexistuje
if not os.path.exists(REC_PATH):
    try:
        os.makedirs(REC_PATH)
    except:
        pass

# Globální proměnné pro nahrávání
recording_file = None
is_recording = False


# Koeficienty matic
SQRT1_2 = np.sqrt(0.5)
SQRT3_2 = np.sqrt(3) / 2
HALF = 0.5
QS_A, QS_B = 0.9239, 0.3827


def find_behringer():
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if "UMC404" in dev['name'].upper() or "BEHRINGER" in dev['name'].upper():
            return i
    return None


def create_hilbert_fir(n=511):
    if n % 2 == 0:
        n += 1
    t = np.arange(n) - (n - 1) // 2
    h = np.zeros(n)
    h[t != 0] = 2 / (np.pi * t[t != 0])
    h *= np.blackman(n)
    return h


h_coeffs = create_hilbert_fir(511)
state_SL = np.zeros(len(h_coeffs) - 1)
state_SR = np.zeros(len(h_coeffs) - 1)


def print_menu():
    rec_status = "!!! NAHRÁVÁM !!!" if is_recording else "připraven"
    print("\n" + "="*78)
    print(
        f"  QUAD LIVE ENCODER v{VERSION} | FS: {current_fs}Hz | Mode: {current_mode.upper()}")
    print(f"  DIGI REKORDÉR: {rec_status}")
    print("="*78)
    print("  MATICE:   [q] SQ | [x] QS | [p] PL2 | [s] Stereo")
    print("  ZÁZNAM:   [r] START nahrávání | [t] STOP nahrávání")
    print("  OVLÁDÁNÍ: [1] 44.1k | [2] 48k | [e] Exit")
    print("="*78)
    print("Příkaz > ", end='', flush=True)


def callback(indata, outdata, frames, time_info, status):
    global state_SL, state_SR, current_mode, recording_file, is_recording
    if status:
        print(status)

    fl, fr, sl, sr = indata[:, 0], indata[:, 1], indata[:, 2], indata[:, 3]

    # UKLÁDÁNÍ DO WAV (4 kanály před maticí)
    if is_recording and recording_file is not None:
        # Vytvoříme ticho pro 6 kanálů
        rec_data = np.zeros((frames, 6), dtype='float32')
        rec_data[:, 0] = fl  # Front Left
        rec_data[:, 1] = fr  # Front Right
        rec_data[:, 2] = 0   # CENTER (Ticho)
        rec_data[:, 3] = 0   # LFE (Ticho)
        rec_data[:, 4] = sl  # Surround Left
        rec_data[:, 5] = sr  # Surround Right
        recording_file.write(rec_data)
        #recording_file.write(indata)

    sl_90, state_SL = lfilter(h_coeffs, 1.0, sl, zi=state_SL)
    sr_90, state_SR = lfilter(h_coeffs, 1.0, sr, zi=state_SR)

    if current_mode == 'SQ':
        lt = fl - (sl_90 * SQRT1_2) + (sr * SQRT1_2)
        rt = fr + (sr_90 * SQRT1_2) - (sl * SQRT1_2)
    elif current_mode == 'QS':
        lt = (fl * QS_A) + (fr * QS_B) - (sl_90 * QS_A) + (sr_90 * QS_B)
        rt = (fr * QS_A) + (fl * QS_B) + (sr_90 * QS_A) - (sl_90 * QS_B)
    elif current_mode == 'PL2':
        lt = fl - (sl_90 * SQRT3_2) - (sr_90 * HALF)
        rt = fr + (sl_90 * HALF) + (sr_90 * SQRT3_2)
    else:
        lt, rt = fl, fr

    out_final = np.zeros((frames, 4))
    out_final[:, 0] = lt * 0.9
    out_final[:, 1] = rt * 0.9
    outdata[:] = out_final


beh_idx = find_behringer()


def run_encoder():
    # PŘIDÁNY TYTO GLOBÁLNÍ PROMĚNNÉ:
    global current_fs, current_mode, state_SL, state_SR, is_recording, recording_file

    stream = sd.Stream(device=(beh_idx, beh_idx), samplerate=current_fs,
                       blocksize=BLOCKSIZE, dtype='float32', channels=(4, 4),
                       callback=callback)
    stream.start()
    print_menu()

    try:
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if r:
                line = sys.stdin.readline().strip().lower()
                if line == 'e':
                    if is_recording:
                        is_recording = False
                        recording_file.close()

                    return False
                elif line == 'r':  # START REC
                    if not is_recording:
                        now = datetime.now().strftime("%Y%m%d-%H%M%S")
                        filename = os.path.join(REC_PATH, f"{now}.wav")
                        # ZMĚNA: channels=6
                        recording_file = sf.SoundFile(filename, mode='x', samplerate=current_fs,
                                                      channels=6, subtype='FLOAT')  
                        is_recording = True
                        print(f"\n>>> Záznam spuštěn: {filename}")
                        print_menu()

                elif line == 't':  # STOP REC
                    if is_recording:
                        is_recording = False
                        recording_file.close()
                        recording_file = None
                        print("\n>>> Záznam uložen.")
                        print_menu()

                elif line == '1':
                    current_fs = 44100
                    return True  # Restart stream
                elif line == '2':
                    current_fs = 48000
                    return True  # Restart stream
                elif line in ['q', 'x', 'p', 's']:
                    modes = {'q': 'SQ', 'x': 'QS', 'p': 'PL2', 's': 'Stereo'}
                    current_mode = modes[line]
                    # Reset fází při změně matice pro čistý start
                    state_SL *= 0
                    state_SR *= 0
                    print_menu()
            time.sleep(0.1)
    except KeyboardInterrupt:
        if is_recording: recording_file.close()
        return False
    finally:
        stream.stop()
        stream.close()


if __name__ == "__main__":
    if beh_idx is None:
        print("!!! Behringer nenalezen")
        sys.exit(1)

    should_run = True
    while should_run:
        should_run = run_encoder()
