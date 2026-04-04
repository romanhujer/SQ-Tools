import sounddevice as sd
import numpy as np
import sys

# Konfigurace - stejná jako u tebe
OUTPUT_DEV = 0  # HDMI TX-NR626
SR = 48000
CHANNELS = 6

def test_callback(outdata, frames, time, status):
    if status: print(status)
    outdata.fill(0)
    # Generujeme bílý šum jen pro aktivní kanál
    noise = np.random.uniform(-0.2, 0.2, frames)
    outdata[:, current_channel] = noise

current_channel = 0
names = ["0: Front Left", "1: Front Right", "2: Center", "3: LFE (Sub)", "4: Surround Left", "5: Surround Right"]

print(f"--- TEST KANÁLŮ NA HDMI (Index {OUTPUT_DEV}) ---")
print("Mačkejte ENTER pro přepnutí na další kanál, 'q' pro konec.")

try:
    with sd.OutputStream(device=OUTPUT_DEV, channels=CHANNELS, samplerate=SR, callback=test_callback):
        while current_channel < CHANNELS:
            print(f"\nAKTIVNÍ KANÁL: {names[current_channel]}")
            cmd = input("Stiskni Enter pro další (nebo 'q'): ")
            if cmd.lower() == 'q': break
            current_channel += 1
except Exception as e:
    print(f"Chyba: {e}")

print("\nTest ukončen.")
