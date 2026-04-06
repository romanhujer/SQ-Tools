#!/bin/bash


cd script.quad.control

# Vytvoření složek pro jazyky  skina
mkdir -p resources/language/resource.language.cs_cz
mkdir -p resources/language/resource.language.en_gb
mkdir -p resources/language/resource.language.en_gb
mkdir -p resources/language/resource.language.en_us
mkdir -p resources/language/resource.language.en_au
mkdir -p resources/language/resource.language.en_nz
mkdir -p resources/skins/Default/720p


# Vytvoření prázdných souborů strings.po
touch resources/language/resource.language.cs_cz/strings.po
touch resources/language/resource.language.en_gb/strings.po
touch resources/language/resource.language.en_us/strings.po
touch resources/language/resource.language.en_au/strings.po
touch resources/language/resource.language.en_nx/strings.po
touch resources/skins/Default/720p/script-quad-control.xml


# Kontrola výsledku
ls -R resources/
