# 🌀 RPi-Quad-Decoder: 1970s Surround Sound Revival

This project breathes new life into forgotten quadraphonic recordings from the 1970s. Using a **Raspberry Pi 5** and modern high-fidelity audio interfaces, we digitally decode analog matrix systems (SQ/QS) and stream them directly to modern Home Theater receivers via HDMI Multichannel PCM.

## 📻 A Bit of History: The Quadraphonic Wars
In the 1970s, engineers aimed to place the listener in the center of the music. However, a "format war" led to several incompatible systems:

* **SQ (Stereo Quadraphonic):** Developed by CBS. It uses 90° phase-shifts to "hide" four channels within two stereo tracks. This is our primary target.
* **QS (Regular Matrix):** Sansui's competing system. Similar to SQ but uses a different mixing matrix for channel distribution.
* **CD-4 (Compatible Discrete 4):** A discrete system by JVC and RCA. 
    > **⚠️ The CD-4 Challenge:** Unlike matrix systems, CD-4 is nearly impossible to decode reliably today. It requires specialized phono cartridges capable of tracking up to 50 kHz (for the subcarrier) and ultra-low capacitance cables. Most vintage discs have suffered groove wear that destroys the high-frequency carrier.

## 🚀 Our Solution: SQ on Raspberry Pi 5
Instead of hunting for expensive and failing vintage hardware decoders, we harness the processing power of the **RPi 5**.

### Current Features:
* **Real-time Processing:** Audio from the turntable enters via a USB Interface (Sound Blaster HD / Behringer UMC series).
* **SQ Matrix Decoding:** Precise digital decoding of phase information using Python (`sounddevice`, `numpy`, `scipy`).
* **Pure HDMI 5.0 Output:** Direct streaming to AV Receivers (e.g., Onkyo TX-NR626) via 24-bit PCM Multichannel. No "fake" DSP like Dolby ProLogic—you hear the mix exactly as it was intended.
* **Dockerized Environment:** Isolated ALSA configuration ensures stability and easy deployment on LibreELEC or Raspberry Pi OS.

### Signal Chain:
`Turntable` ➔ `USB Audio Interface` ➔ `Raspberry Pi 5 (Python Engine)` ➔ `HDMI` ➔ `AV Receiver (Multichannel PCM)`

## 🛠 Installation & Usage
The project runs within a Docker container to manage audio dependencies and hardware access.

```bash
# Clone the repository
git clone [https://github.com/yourusername/rpi-quad-decoder.git](https://github.com/yourusername/rpi-quad-decoder.git)
cd rpi-quad-decoder

# Build the image
docker build -t sq-decoder -f docker/Dockerfile .

# Run the decoder bridge
./run.sh# SQ-Tools
```

📝 Roadmap (To-Do)
* QS Matrix: Implementation of the Sansui QS decoding matrix.

* Direct USB Turntable Support: Optimization for turntables with built-in USB outputs.

* Advanced De-Clicker: Real-time digital impulse noise reduction to clean up vintage vinyl pops without affecting transients.

* Offline DTS-CD Converter: A tool to transcode 5.1 DTS-CD ISOs into SQ-encoded Stereo for recording onto analog Reel-to-Reel or Cassette tapes.
