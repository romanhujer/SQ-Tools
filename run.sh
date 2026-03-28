#!/bin/sh

cat $0

docker run -it --rm \
  --name sq-test \
  --privileged \
  --net=host \
  --device /dev/snd \
  --device /dev/dri \
  -v /dev/snd:/dev/snd \
  -v /dev/dri:/dev/dri \
  sq-decoder


