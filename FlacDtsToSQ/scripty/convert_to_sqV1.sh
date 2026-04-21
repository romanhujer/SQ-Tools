#!/bin/bash
# --- KONFIGURACE ---

# Zde zadej cestu k tvému 1.5GB archivu
INPUT_FLAC="Phil_Collins_192-40.flac"
INPUT_CUE="none.cue"
TMP_DIR="tmp_processing"
FINAL_DIR="enc"
PYTHON_SCRIPT="script/DtsToSQ.py"
VENV_PATH="venv/bin/activate"

# 1. Vytvoření adresářů
echo "--- Vytvářím adresáře ---"
mkdir -p "$TMP_DIR"
mkdir -p "$FINAL_DIR"

# 2. Rozbalení FLACu na 4-kanálový PCM (pro Python)
# Místo DTS teď čteme tvůj Hi-Res FLAC
echo "--- Expanduji FLAC pro SQ Encoding ---"
if [ -f "$INPUT_FLAC" ]; then
# -ar 96000 zajistí, že z 192k uděláme 96k
    # -sample_fmt s24 zachová 24-bitovou hloubku
    # Oprava pro Mac: explicitně definujeme kodek pcm_s24le a vzorkování 96k
    ffmpeg -i "$INPUT_FLAC" -ar 96000 -c:a pcm_s24le "$TMP_DIR/multichannel.wav" -y
    #ffmpeg -i "$INPUT_FLAC" -ar 96000 -sample_fmt s24 -f wav "$TMP_DIR/multichannel.wav" -y
    #ffmpeg -i "$INPUT_FLAC" -f wav "$TMP_DIR/multichannel.wav" -y
else    echo "Chyba: Vstupní FLAC $INPUT_FLAC nebyl nalezen!"
    exit 1
fi

# 3. SQ Encoding (Python)
echo "--- Spouštím SQ Encoding (Python) ---"
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
    python3 "$PYTHON_SCRIPT"
else
    # Pokud venv nemáš, zkusíme klasický python3
    python3 "$PYTHON_SCRIPT" || { echo "Chyba při spouštění Pythonu!"; exit 1; }
fi

# 4. Rozstříhání podle CUE nebo převod celého souboru
echo "--- Zpracování finálního audia (SQ FLAC) ---"

if [ -f "$INPUT_CUE" ]; then
    echo "Nalezen CUE soubor, stříhám na jednotlivé skladby..."
    # breakpointy z CUE -> shnsplit do finální složky
    cuebreakpoints "$INPUT_CUE" | shnsplit -o flac -f "$INPUT_CUE" \
    -t "%n %t" -d "$FINAL_DIR" "$TMP_DIR/master_sq.wav"
    
    # Zápis tagů
    cd "$FINAL_DIR"
    cuetag "../$INPUT_CUE" [0-9]*.flac
    cd ..
else
    echo "CUE soubor nenalezen. Ukládám jako jeden SQ FLAC..."
    # Použijeme název podle původního FLACu s příponou _SQ
    OUTPUT_NAME=$(basename "$INPUT_FLAC" .flac)
    ffmpeg -i "$TMP_DIR/master_sq.wav" -c:a  flac -compression_level 8 "$FINAL_DIR/${OUTPUT_NAME}_SQ.flac"
    echo "Hotovo: SQ Master uložen do $FINAL_DIR"
fi

# 5. Úklid
echo "--- Čištění TMP adresáře ---"
rm -f "$TMP_DIR/multichannel.wav"
rm -f "$TMP_DIR/master_sq.wav"

echo "================================================="
echo "HOTOVO! SQ verze je připravena v: $FINAL_DIR"
echo "================================================="
