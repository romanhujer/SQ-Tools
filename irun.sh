#!/bin/sh

echo ">>> Zastavuji starý proces..."
docker stop quuad_processor 2>/dev/null

echo ">>> Sestavuji aktuální verzi (včetně změn v bridge.py)..."
# Přidáme --no-cache jen pro jistotu, nebo se spolehni na Docker, 
# ale smažeme starý obraz, aby se vynutil rebuild vrstvy s COPY
docker build -t quadproc .

echo ">>> Spouštím Quad Processor..."
docker run -it --init --rm \
  --name quuad_processor \
  --privileged \
  --net=host \
  --group-add audio \
  --device /dev/snd:/dev/snd \
  --device /dev/dri:/dev/dri \
  -v /tmp:/tmp \
  quadproc:latest
