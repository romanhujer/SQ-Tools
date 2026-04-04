import sounddevice as sd
import numpy as np
import time

# RUČNÍ NASTAVENÍ PODLE TVÉHO VÝPIU
INPUT_DEV = 1   # USB Sound Blaster HD: Audio (hw:2,0)
OUTPUT_DEV = 5  # hdmi (hw:0,0) - Tvoje Onkyo

def callback(indata, outdata, frames, time_info, status):
    if status:
        print(f"Status: {status}", flush=True)
    
    # VU metr
    rms = np.sqrt(np.mean(indata**2))
    meter = "#" * int(rms * 50)
    print(f"Level: [{meter:<50}] {rms:.4f}", end='\r', flush=True)
    
    outdata[:] = indata

print(f"Startuji most: SBX(ID:{INPUT_DEV}) -> ONKYO(ID:{OUTPUT_DEV})")

# Zkusíme nejdřív 48000 (standard pro HDMI), pak 44100
for rate in [48000, 44100]:
    try:
        print(f"Zkouším frekvenci: {rate} Hz...")
        with sd.Stream(device=(INPUT_DEV, OUTPUT_DEV),
                       samplerate=rate, 
                       channels=2, 
                       dtype='float32',
                       blocksize=2048, # Větší buffer pro stabilitu
                       callback=callback):
            print(f"BĚŽÍME NA {rate} Hz!")
            while True:
                time.sleep(1)
    except Exception as e:
        print(f"Frekvence {rate} Hz nefunguje: {e}")

print("Nepodařilo se spustit stream na žádné frekvenci.")
