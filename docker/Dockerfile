FROM python:3.11-slim

# Instalace audio knihoven
RUN apt-get update && apt-get install -y \
    libportaudio2 \
    libasound2 \
    alsa-utils \
    && rm -rf /var/lib/apt/lists/*

# Instalace Python modulů
RUN pip install sounddevice numpy scipy

# Pracovní adresář v kontejneru
WORKDIR /app

# Kopírujeme pouze audio bridge
COPY audio-bridge/bridge.py .

# Spuštění pouze pythonu
CMD ["python", "bridge.py"]
