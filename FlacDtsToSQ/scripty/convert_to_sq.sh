#!/bin/bash
set -e  # Zastavit při jakékoli chybě

# --- KONTROLA PARAMETRŮ ---
if [ "$#" -lt 2 ]; then
    echo "Použití: ./scripty/convert_to_sq.sh <soubor> <matice>"
    echo "Příklad: ./scripty/convert_to_sq.sh nahrávka.flac PL2"
    exit 1
fi

INPUT_FILE=$1
MATRIX=$2
TMP_DIR="tmp_processing"
VENV_PYTHON="./venv/bin/python3"
FINAL_DIR="final"

mkdir -p "$TMP_DIR"
mkdir -p "$FINAL_DIR"

# --- DETEKCE FORMÁTU A DEKÓDOVÁNÍ ---
EXTENSION="${INPUT_FILE##*.}"
#FILENAME=$(basename "$INPUT_FILE" ."$EXTENSION")

# 1. Získání čistého jména souboru bez cesty a bez jakékoli přípony (.flac, .wav, .w64)
# Tento řádek funguje bezpečně i na Macu
BASE_NAME=$(basename "$INPUT_FILE")
FILENAME="${BASE_NAME%.*}"

# 2. Definice výstupních cest
OUTPUT_MASTER="$FINAL_DIR/${FILENAME}_${MATRIX}_HiRes.flac"
OUTPUT_COMPAT="$FINAL_DIR/${FILENAME}_${MATRIX}.flac"


echo "--- Zjištěn formát: $EXTENSION ---"

case "$EXTENSION" in
    flac|FLAC)
        echo "Dekóduji FLAC (192k -> 96k)..."
        ffmpeg -i "$INPUT_FILE" -ar 96000 -c:a pcm_s24le "$TMP_DIR/multichannel.w64" -y
        ;;
    dts|DTS)
        echo "Dekóduji DTS (vyžaduje -strict -2)..."
        ffmpeg -strict -2 -i "$INPUT_FILE" -c:a pcm_s24le "$TMP_DIR/multichannel.w64" -y
        ;;
    wav|WAV|w64|W64)
        echo "Zpracovávám WAV přímo..."
        ffmpeg -i "$INPUT_FILE" -ar 96000 -c:a pcm_s24le "$TMP_DIR/multichannel.w64" -y
        ;;
    *)
        echo "Chyba: Nepodporovaný formát souboru: $EXTENSION"
        exit 1
        ;;
esac

# --- SQ/PL2 ENCODING (PYTHON) ---
echo "--- Spouštím maticový encoding: $MATRIX ---"

if [ -f "$VENV_PYTHON" ]; then
    $VENV_PYTHON ./scripty/wavToSQ.py "$TMP_DIR/multichannel.w64" "$TMP_DIR/master_encoded.w64" "$MATRIX"
else
    echo "Varování: VENV nenalezen, zkouším systémový python..."
    python3 ./scripty/wavToSQ.py "$TMP_DIR/multichannel.w64" "$TMP_DIR/master_encoded.w64" "$MATRIX"
fi


# --- FINÁLNÍ FLAC ---
# Teď už proměnná $OUTPUT_MASTER nebude prázdná
# 1. Hi-Res Master (zachová 24-bit z Pythonu)
case "$EXTENSION" in
    flac|FLAC)
        echo "--- Vytvářím Hi-Res Master: $OUTPUT_MASTER ---"
        ffmpeg -i "$TMP_DIR/master_encoded.w64" -c:a flac -compression_level 12 "$OUTPUT_MASTER" -y
        # 2. Kompatibilní 16-bit / 48 kHz
        echo "--- Vytvářím: $OUTPUT_COMPAT ---"
        ffmpeg -i "$TMP_DIR/master_encoded.w64" -ar 48000 -sample_fmt s16 -c:a flac "$OUTPUT_COMPAT" -y
        ;;
    dts|DTS)
        echo "--- Vytvářím: $OUTPUT_COMPAT ---"
        ffmpeg -i "$TMP_DIR/master_encoded.w6:x4" -ar 48000 -sample_fmt s16 -c:a flac "$OUTPUT_COMPAT" -y
        ;;    
    wav|WAV|w64|W64)
        echo "--- Vytvářím Hi-Res Master: $OUTPUT_MASTER ---"
        ffmpeg -i "$TMP_DIR/master_encoded.w64" -c:a flac -compression_level 12 "$OUTPUT_MASTER" -y
        # 2. Kompatibilní 16-bit / 48 kHz
        echo "--- Vytvářím: $OUTPUT_COMPAT ---"
        ffmpeg -i "$TMP_DIR/master_encoded.w64" -ar 48000 -sample_fmt s16 -c:a flac "$OUTPUT_COMPAT" -y
        ;;    
    *)
        echo "Chyba: Nepodporovaný formát souboru: $EXTENSION"
        exit 1
        ;;
esac        



if [ -f "$INPUT_CUE" ]; then
    echo "Nalezen CUE soubor, stříhám na jednotlivé skladby..."
    # breakpointy z CUE -> shnsplit do finální složky
    cuebreakpoints "$INPUT_CUE" | shnsplit -o flac -f "$INPUT_CUE" \
    -t "%n %t" -d "$FINAL_DIR" "$TMP_DIR/master_sq.wav"
    
    # Zápis tagů
    cd "$FINAL_DIR"
    cuetag "../$INPUT_CUE" [0-9]*.flac
    cd ..
fi


# Úklid
rm -f "$TMP_DIR/multichannel.*"
rm -f "$TMP_DIR/master_encoded.*"



echo "================================================="
echo "HOTOVO!"
echo "Master: $OUTPUT_MASTER"
echo "Kompatibilní: $OUTPUT_COMPAT"
echo "================================================="
