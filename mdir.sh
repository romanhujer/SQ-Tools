# Vytvoření složek pro jazyky
mkdir -p resources/language/resource.language.cs_cz
mkdir -p resources/language/resource.language.en_gb

# Vytvoření prázdných souborů strings.po
touch resources/language/resource.language.cs_cz/strings.po
touch resources/language/resource.language.en_gb/strings.po

# Kontrola výsledku
ls -R resources/
