# Použijeme stabilní Python obraz
FROM python:3.11-slim

# Potlačení interaktivních dotazů při instalaci balíčků
ENV DEBIAN_FRONTEND=noninteractive

# 1. Instalace systémových audio knihoven a nástrojů (amixer/alsamixer)
# libasound2-dev a libportaudio2 jsou klíčové pro sounddevice
# alsa-utils nám umožní ovládat bypass karty (amixer)
RUN apt-get update && apt-get install -y \
    libasound2-dev \
    libportaudio2 \
    libasound2 \
    alsa-utils \
    && rm -rf /var/lib/apt/lists/*

# 2. Instalace Python modulů přímo (bez requirements.txt pro jednoduchost)
# Scipy potřebujeme pro budoucí Hilbertovu transformaci a De-Clicker
RUN pip install --no-cache-dir sounddevice numpy scipy

# 3. Pracovní adresář v kontejneru
WORKDIR /app

# 4. Kopírování skriptu do kontejneru
# Předpokládám, že bridge.py máš ve složce audio-bridge
COPY quadproc/quadDSP.py .

# 5. Spuštění .py
# Používáme -u (unbuffered), aby se výpisy v Dockeru zobrazovaly okamžitě
CMD ["python", "-u", "quadDSP.py"]
