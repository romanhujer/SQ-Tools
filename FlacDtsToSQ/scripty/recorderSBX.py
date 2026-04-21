#!/usr/bin/env /Users/hujer/myRec/venv/bin/python3
# -*- coding: utf-8 -*-

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sounddevice as sd
import soundfile as sf
import numpy as np
import sys
import os
from datetime import datetime

# --- KONFIGURACE ---
FS = 48000
BLOCKSIZE = 4096
FILE_CHANNELS = 6  # Výsledný soubor bude 5.1 (L, R, C, LFE, Ls, Rs)
REC_PATH = "/Users/hujer/myRec"

if not os.path.exists(REC_PATH):
    os.makedirs(REC_PATH)

# --- AUTOMATICKÁ DETEKCE ZAŘÍZENÍ ---
def find_devices():
    devices = sd.query_devices()
    in_id = None
    out_id = None
    
    for i, dev in enumerate(devices):
        name = dev['name'].upper()
        # Hledáme BlackHole (vstup)
        if "BLACKHOLE" in name:
            in_id = i
        # Hledáme Behringer (výstup)
        if "USB" in name:
            out_id = i
            
    return in_id, out_id

print(sd.query_devices())

ID_IN, ID_OUT = find_devices() 
ID_OUT = ID_OUT - 1

if ID_IN is None or ID_OUT is None:
    print(f"CHYBA: Zařízení nenalezena! (Vstup: {ID_IN}, Výstup: {ID_OUT})")
    print(sd.query_devices())
    sys.exit()

# Zjistíme kolik kanálů zařízení SKUTEČNĚ vyžadují (důležité pro BlackHole)
CHANNELS_IN_MAX = sd.query_devices(ID_IN)['max_input_channels']
CHANNELS_OUT_MAX = sd.query_devices(ID_OUT)['max_output_channels']

# Globální stavy
is_recording = False
is_paused = False
current_file = None

def get_new_filename():
    now = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(REC_PATH, f"AMA40_{now}.w64") # Apple Music Atmos 4.0

def callback(indata, outdata, frames, time, status):
    global is_recording, is_paused, current_file
    if status:
        print(status, file=sys.stderr)

    # 1. TRVALÝ PŘÍPOSLECH (První 4 kanály z BlackHole do 4 kanálů Behringeru)
    # Musíme zajistit, aby indexy nepřesáhly možnosti HW
    outdata[:frames, :2] = indata[:frames, :2]

    # 2. ZÁPIS DO SOUBORU (Transformace 4.0 na 5.1)
    if is_recording and not is_paused and current_file is not None:
        data_51 = np.zeros((frames, FILE_CHANNELS), dtype='float32')
        # Namapování (Atmos/Quad -> 5.1 Layout)
        data_51[:, 0] = indata[:, 0] # L
        data_51[:, 1] = indata[:, 1] # R
        # 2 = Center (Ticho), 3 = LFE (Ticho)
        data_51[:, 4] = indata[:, 2] # Ls
        data_51[:, 5] = indata[:, 3] # Rs
        
        current_file.write(data_51)

print(f"--- QUAD-TO-5.1 AUTO-DETECT RECORDER ---")
print(f"Vstup: [{ID_IN}] {sd.query_devices(ID_IN)['name']} ({CHANNELS_IN_MAX} ch)")
print(f"Výstup: [{ID_OUT}] {sd.query_devices(ID_OUT)['name']} ({CHANNELS_OUT_MAX} ch)")
print(f"Vzorkování: {FS} Hz | Ukládání: 5.1 WAV (24-bit)")

try:
    # Klíčová změna: Otevíráme zařízení s jejich NATIVNÍM počtem kanálů
    with sd.Stream(device=(ID_IN, ID_OUT), 
                   samplerate=FS, 
                   blocksize=BLOCKSIZE,
                   channels=(CHANNELS_IN_MAX,CHANNELS_OUT_MAX), 
                   callback=callback):
        
        while True:
            cmd = input("\n[R]ecord | [P]ause | [S]top | [E]xit: ").upper()
            
            if cmd == 'R':
                if not is_recording:
                    fname = get_new_filename()
                    current_file = sf.SoundFile(fname, mode='x', samplerate=FS, 
                                              channels=FILE_CHANNELS, subtype='PCM_24')
                    is_recording = True
                    is_paused = False
                    print(f">>> NAHRÁVÁM DO: {fname}")
                elif is_paused:
                    is_paused = False
                    print(">>> POKRAČUJI (PAUZA ZRUŠENA)")

            elif cmd == 'P':
                if is_recording and not is_paused:
                    is_paused = True
                    print("|| PAUZA")

            elif cmd == 'S':
                if is_recording:
                    is_recording = False
                    current_file.close()
                    current_file = None
                    print("■ STOP - Soubor uložen.")

            elif cmd == 'E':
                if is_recording:
                    current_file.close()
                break

except Exception as e:
    print(f"\n[FATAL ERROR]: {e}")