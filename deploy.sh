#!/bin/bash

# 1. Definice cest
ADDON_DIR="script.quad.control"
XML_FILE="$ADDON_DIR/addon.xml"
BUILD_DIR="builds"

mkdir -p $BUILD_DIR

# 2. Získání verze - hledáme POUZE řádek začínající <addon a v něm verzi
CURRENT_VERSION=$(grep "<addon" "$XML_FILE" | grep -oP 'version="\K[0-9.]+')

if [ -z "$CURRENT_VERSION" ]; then
    echo "Chyba: Nepodařilo se najít verzi doplňku v $XML_FILE"
    exit 1
fi

echo "Aktuální verze doplňku: $CURRENT_VERSION"

# 3. Zvýšení patch verze (poslední číslo za tečkou)
BASE_VERSION=$(echo $CURRENT_VERSION | cut -d. -f1-2)
PATCH_VERSION=$(echo $CURRENT_VERSION | cut -d. -f3)
NEW_PATCH=$((PATCH_VERSION + 1))
NEW_VERSION="$BASE_VERSION.$NEW_PATCH"

echo "Nová verze doplňku: $NEW_VERSION"

# 4. Aktualizace addon.xml - nahradíme verzi pouze na řádku s <addon
sed -i "/<addon/s/version=\"$CURRENT_VERSION\"/version=\"$NEW_VERSION\"/" "$XML_FILE"

# 5. Vytvoření ZIP archivu
ZIP_NAME="script.quad.control-$NEW_VERSION.zip"
echo "Vytvářím archiv: $BUILD_DIR/$ZIP_NAME"

zip -r "$BUILD_DIR/$ZIP_NAME" "$ADDON_DIR" -x "*/.*" -x ".git/*" -x ".vscode/*" -x "*/__pycache__/*"

# 6. Odeslání do Kodi
echo "Odesílám do Kodi..."
scp "$BUILD_DIR/$ZIP_NAME" myKodi:/storage/

echo "Hotovo! V addon.xml je nyní verze $NEW_VERSION"