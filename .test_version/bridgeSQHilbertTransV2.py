import sounddevice as sd
import numpy as np
from scipy.signal import lfilter, firwin
import sys

# --- KONFIGURACE ---
SAMPLERATE = 48000
BLOCKSIZE = 2048 
OUTPUT_DEV = 4   # Onkyo HDMI

# --- TVORBA HILBERTOVA FILTRU ---
def create_hilbert_fir(n=127):
    # Vytvoří koeficienty pro 90° fázový posun
    if n % 2 == 0: n += 1
    t = np.arange(n) - (n - 1) // 2
    h = np.zeros(n)
    h[t != 0] = 2 / (np.pi * t[t != 0])
    h *= np.hamming(n) # Okno pro eliminaci překmitů
    return h

h_coeffs = create_hilbert_fir(127)

# STAVY FILTRŮ (aby to nelupalo mezi bloky)
state_L = np.zeros(len(h_coeffs) - 1)
state_R = np.zeros(len(h_coeffs) - 1)

def callback(indata, outdata, frames, time, status):
    global state_L, state_R
    if status:
        print(status, file=sys.stderr)

    # Vstup
    L = indata[:, 0].astype(np.float32) / 32768.0
    R = indata[:, 1].astype(np.float32) / 32768.0

    # 1. Fázový posun o 90° (Plynulý FIR)
    # lfilter vrací (vysledek, novy_stav)
    L_90, state_L = lfilter(h_coeffs, 1.0, L, zi=state_L)
    R_90, state_R = lfilter(h_coeffs, 1.0, R, zi=state_R)

    # 2. SQ MATICE
    out_6ch = np.zeros((frames, 6), dtype=np.float32)
    COEFF = 0.7071
    
    # Předek (FL, FR)
    out_6ch[:, 0] = L
    out_6ch[:, 1] = R
    
    # Zadek (SL, SR) - SQ Standard
    # SL = -0.707 * L_90 + 0.707 * R
    out_6ch[:, 4] = (-COEFF * L_90) + (COEFF * R)
    # SR = 0.707 * L - 0.707 * R_90
    out_6ch[:, 5] = (COEFF * L) - (COEFF * R_90)

    # 3. Limiter a výstup
    out_6ch = np.clip(out_6ch * 0.85, -1.0, 1.0)
    outdata[:] = (out_6ch * 32767.0).astype(np.int16)

# --- START ---
print(f"FIR SQ Dekodér běží na HDMI {OUTPUT_DEV}...")
try:
    with sd.Stream(device=(1, OUTPUT_DEV), samplerate=SAMPLERATE, blocksize=BLOCKSIZE,
                   channels=(2, 6), dtype='int16', callback=callback):
        while True:
            sd.sleep(1000)
except KeyboardInterrupt:
    print("\nUkončeno.")
    