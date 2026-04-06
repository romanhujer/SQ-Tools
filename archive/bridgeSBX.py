import sounddevice as sd
import numpy as np
import os
import sys
import select

# --- KONFIGURACE ---
INPUT_DEV = 1    # USB SBX (hw:2,0)
OUTPUT_ANALOG = 1 
OUTPUT_HDMI = 4  
SAMPLERATE = 96000
BLOCKSIZE = 8192 

mode = 1 # Start v SQ
COEFF = 0.707

# Stream pro Analogový Multiroom (RCA)
analog_out = sd.OutputStream(device=OUTPUT_ANALOG, channels=2, dtype='int16', samplerate=SAMPLERATE)
analog_out.start()

def callback(indata, outdata, frames, time, status):
    # 1. Signál z gramofonu
    in_f = indata.astype(np.float32) / 32768.0
    L, R = in_f[:, 0], in_f[:, 1]
    
    # 2. Výpočet pro HDMI (Onkyo 5.1)
    hdmi_out = np.zeros((frames, 6), dtype=np.float32)
    hdmi_out[:, 0], hdmi_out[:, 1] = L, R
    
    if mode == 1: # SQ Matrix
        hdmi_out[:, 4] = (L - COEFF * R) * COEFF
        hdmi_out[:, 5] = (R + COEFF * L) * COEFF
    elif mode == 2: # QS Matrix
        hdmi_out[:, 0], hdmi_out[:, 1] = L + 0.414*R, R + 0.414*L
        hdmi_out[:, 4], hdmi_out[:, 5] = L - 0.414*R, R - 0.414*L
    
    # Zápis do HDMI a Analogu
    outdata[:] = (hdmi_out * 32767.0).astype(np.int16)
    analog_out.write(indata)

def check_keyboard():
    """Funkce pro neblokující čtení klávesnice v Linuxu"""
    if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
        return sys.stdin.readline().strip().lower()
    return None

try:
    os.system("amixer -c 2 sset 'PCM Capture Source',0 'Line'")
    os.system("amixer -c 2 sset 'PCM',0 100% unmute")

    with sd.Stream(device=(INPUT_DEV, OUTPUT_HDMI),
                   samplerate=SAMPLERATE,
                   blocksize=BLOCKSIZE,
                   channels=(2, 6), 
                   dtype='int16',
                   callback=callback):
        
        print("\n" + "="*40)
        print("--- KVADROFONNÍ CENTRÁLA BĚŽÍ ---")
        print("VÝSTUP 1: Onkyo HDMI (5.1 Dekodér)")
        print("VÝSTUP 2: Multiroom RCA (Analog Stereo)")
        print("="*40)
        print("KLÁVESY (napiš písmeno a potvrď Enter):")
        print("  s -> STEREO")
        print("  q -> SQ MATRIX (CBS)")
        print("  x -> QS MATRIX (Sansui)")
        print("  e -> KONEC")
        print("-" * 40)

        while True:
            cmd = check_keyboard()
            if cmd == 'e':
                break
            elif cmd in ['s', 'q', 'x']:
                mode = {'s': 0, 'q': 1, 'x': 2}[cmd]
                m_name = ["STEREO", "SQ MATRIX", "QS MATRIX"][mode]
                print(f"[*] AKTIVNÍ REŽIM: {m_name}")
            
            # Malá pauza, aby procesor netopil na prázdno
            sd.sleep(100)

except Exception as e:
    print(f"\nCHYBA: {e}")
finally:
    analog_out.stop()
    analog_out.close()
    print("\nDekodér ukončen.")