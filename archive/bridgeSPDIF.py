import sounddevice as sd
import numpy as np
import os

# --- KONFIGURACE ---
INPUT_DEV = 1    # USB SBX (hw:2,0)
OUTPUT_HDMI = 5  # HDMI Onkyo
OUTPUT_SPDIF = 2 # SBX S/PDIF
SAMPLERATE = 48000
BLOCKSIZE = 4096 

mode = 1 # SQ
COEFF = 0.707

# Stream pro Multiroom (2 kanály)
spdif_stream = sd.OutputStream(device=OUTPUT_SPDIF, channels=2, dtype='int16', samplerate=SAMPLERATE)
spdif_stream.start()

def callback(indata, outdata, frames, time, status):
    # 1. Dekódování pro HDMI (outdata - nyní 6 kanálů)
    in_f = indata.astype(np.float32) / 32768.0
    L, R = in_f[:, 0], in_f[:, 1]
    
    # Příprava 6 kanálů pro 5.1
    # 0:FL, 1:FR, 2:C, 3:LFE, 4:SL, 5:SR
    hdmi_out = np.zeros((frames, 6), dtype=np.float32)
    hdmi_out[:, 0], hdmi_out[:, 1] = L, R # Přední pár
    
    if mode == 1: # SQ Matrix
        hdmi_out[:, 4] = (L - COEFF * R) * COEFF # Zadní L (Surround)
        hdmi_out[:, 5] = (R + COEFF * L) * COEFF # Zadní R (Surround)
    elif mode == 2: # QS Matrix
        hdmi_out[:, 0], hdmi_out[:, 1] = L + 0.414*R, R + 0.414*L
        hdmi_out[:, 4], hdmi_out[:, 5] = L - 0.414*R, R - 0.414*L
    
    # Zápis do HDMI (Onkyo by nyní mělo hlásit 5.1 nebo Multich 5.1)
    outdata[:] = (hdmi_out * 32767.0).astype(np.int16)
    
    # 2. Kopie do Multiroomu (SBX S/PDIF)
    spdif_stream.write(indata)

try:
    os.system("amixer -c 2 sset 'PCM Capture Source',0 'Line'")
    os.system("amixer -c 2 sset 'PCM',0 100% unmute")

    # ZMĚNA: channels=(2, 6) namísto (2, 8)
    with sd.Stream(device=(INPUT_DEV, OUTPUT_HDMI),
                   samplerate=SAMPLERATE,
                   blocksize=BLOCKSIZE,
                   channels=(2, 6), 
                   dtype='int16',
                   callback=callback):
        
        print("\n--- 5.1 DEKODÉR AKTIVNÍ ---")
        print("Onkyo: HDMI 5.1 | Multiroom: S/PDIF 2.0")
        print("Menu: s=Stereo, q=SQ, x=QS, e=Konec")
        
        while True:
            cmd = input().lower().strip()
            if cmd == 'e': break
            elif cmd in ['s','q','x']:
                mode = {'s':0, 'q':1, 'x':2}[cmd]
                print(f"Mód: {['STEREO','SQ','QS'][mode]}")

except Exception as e:
    # Pokud to hodí chybu, znamená to, že HDMI trvá na 8 kanálech (7.1)
    print(f"\nCHYBA: {e}")
    print("Tip: Pokud to spadlo, tvůj HDMI ovladač vyžaduje 8 kanálů (7.1) i pro 5.1 zvuk.")
finally:
    spdif_stream.stop()
    spdif_stream.close()
    