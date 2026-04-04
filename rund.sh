#!/bin/sh
# ^--- TENTO ŘÁDEK MUSÍ BÝT ÚPLNĚ PRVNÍ (Shebang)

# Přejdeme do správného adresáře
cd /storage/myapp/

# Nastavení cest pro LibreELEC (Docker)
export PATH="/usr/bin:/usr/sbin:/storage/.kodi/addons/service.system.docker/bin:$PATH"

# Počkáme, dokud docker daemon opravdu nežije
until docker ps >/dev/null 2>&1; do
  echo ">>> QuadDSP: Čekám na Docker daemon..."
  sleep 2
done

echo ">>> Čištění starých kontejnerů..."
docker rm -f quad_dsp >/dev/null 2>&1

echo ">>> Sestavení a start Quad DSP..."
docker build -t quadproc . 

# Spuštění - přidal jsem --restart always přímo do dockeru
docker run -d \
  --name quad_dsp \
  --restart always \
  --privileged \
  --net=host \
  --group-add audio \
  --device /dev/snd:/dev/snd \
  -v /tmp:/tmp \
  quadproc:latest \
  python3 quadDSP.py --daemon

# Kontrolní smyčka pro logy systemd
while true; do  
  echo ">>> QuadDSP status: $(docker inspect -f '{{.State.Status}}' quad_dsp)"
  sleep 3600
done