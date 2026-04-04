#!/bin/sh
#
docker run --rm --device /dev/snd quadproc:latest python3 -c "import pyaudio; p = pyaudio.PyAudio(); [print(f'Index {i}: {p.get_device_info_by_index(i).get(\"name\")}') for i in range(p.get_device_count())]; p.terminate()"

