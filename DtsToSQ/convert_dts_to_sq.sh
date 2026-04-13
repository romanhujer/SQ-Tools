
#!/bin/bash

# --- KONFIGURACE ---
INPUT_WAV="music/OnAir.wav"
INPUT_CUE="music/OnAir.cue"
TMP_DIR="tmp_processing"
FINAL_DIR="OnAir_MH"
PYTHON_SCRIPT="DtsToSQ.py"
VENV_PATH="venv/bin/activate"

# 1. Vytvoření adresářů
echo "--- Vytvářím adresáře ---"
mkdir -p "$TMP_DIR"
mkdir -p "$FINAL_DIR"

# 2. Dekódování DTS na 6-kanálový PCM (Mezistav)
echo "--- Dekódování DTS na 6 kanálů (FFmpeg) ---"
ffmpeg -i "$INPUT_WAV" -f wav "$TMP_DIR/multichannel.wav" -y

# 3. SQ Encoding (Python)
echo "--- Spouštím SQ Encoding (Python) ---"
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
    # Upravíme Python skript, aby bral cesty z argumentů, nebo ho prostě spustíme
    # Předpokládáme, že DtsToSQ.py čte 'tmp_processing/multichannel.wav' 
    # a zapisuje do 'tmp_processing/master_sq.wav'
    python3 "$PYTHON_SCRIPT"
else
    echo "Chyba: Virtuální prostředí nenalezeno!"
    exit 1
fi

# 4. Rozstříhání podle CUE do finálního adresáře
echo "--- Rozstříhání na jednotlivé skladby (SQ FLAC) ---"
if [ -f "$INPUT_CUE" ]; then
    # breakpointy z CUE -> shnsplit do finální složky
    cuebreakpoints "$INPUT_CUE" | shnsplit -o flac -f "$INPUT_CUE" \
    -t "%n %t" -d "$FINAL_DIR" "$TMP_DIR/master_sq.wav"
    
    # Zápis tagů (Artist, Album, atd.)
    cd "$FINAL_DIR"
    cuetag "../$INPUT_CUE" [0-9]*.flac
    cd ..
else
    echo "Chyba: CUE soubor nenalezen, stříhání nebude provedeno."
fi

# 5. Úklid
echo "--- Čištění TMP adresáře ---"
rm -rf "$TMP_DIR"

echo "================================================="
echo "HOTOVO! Tvoje SQ skladby jsou v: $FINAL_DIR"
echo "================================================="
