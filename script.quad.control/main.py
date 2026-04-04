#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mapi.py - Multi-Matrix Quadraphonic Digital Signal Processor (main kodi plugin)
Location: Jablonec nad Nisou, Czechia (2026)
Author: Roman Hujer

DESCRIPTION:
This processor performs real-time decoding of legacy matrix quadraphonic 
formats (SQ, QS, Matrix H, Dolby Stereo/Surround, PL II) from a 2-channel 
input into a 5.1 LPCM output via HDMI. It utilizes 64-bit floating-point 
precision, Hilbert transform phase-shifting, and high-accuracy 
trigonometric constants for bit-perfect spatial reconstruction.

LICENSE:
Copyright (C) 2026 - Roman Hujer
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""

import xbmcgui
import xbmcaddon
import os

def get_s(string_id):
    # Inicializace uvnitř funkce je v Kodi 19+ jistější
    try:
        s = xbmcaddon.Addon().getLocalizedString(string_id)
        return s if s else f"ID:{string_id}"
    except:
        return f"ERR:{string_id}"

STATUS_FILE = '/tmp/quad_status'
CMD_FILE = '/tmp/quad_cmd'

def get_current_info():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                s = f.read().strip().split('|')
                # Bezpečné formátování: pokud get_s(30008) selže, nezhroutí se to
                info = f"{s[0]}:{s[1]} ({s[2]}/{s[3]})"
                template = get_s(30408)
                return template.replace("%s", info) if "%s" in template else f"{template} {info}"
        except:
            pass
    return get_s(30409)

def run():
    dialog = xbmcgui.Dialog()
    
    options = [
        get_s(30001), # SQ (CBS)
        get_s(30002), # QS (Sansui)
        get_s(30003), # Matrix H (BBC)
        get_s(30004), # Stereo-4 (Dynaquad)
        get_s(30005), # Dolby Stereo (Dolby Surround)
        get_s(30006), # Dolby Prologic II 
        get_s(30009), # Bypass 4ch for external decoder
        get_s(30010), # Stereo

        get_s(30101), # 44100 Hz
        get_s(30102), # 48000 Hz
        get_s(30103), # 96000 Hz
        get_s(30104), # 192000 Hz

        get_s(30201), # 16bit
        get_s(30202), # 24bit

        get_s(30501), # Center ON/OFF
        get_s(30502), # De-clicker ON/OFF
        
        get_s(30401), # DSP Start
        get_s(30402), # DSP Stop 
    ]
    
    cmds = ['mode:sq', 'mode:qs', 'mode:matrixh', 'mode:stereo4', 'mode:dolby', 'mode:pl2', 'mode:bypass','mode:stereo', '1','2','3','4','7','8', 'toggle:center', 'toggle:filter', 'dsp:start', 'dsp:stop']

    title = f"{get_s(30000)} - {get_current_info()}"
    sel = dialog.select(title, options)
    
    if sel >= 0:
        try:
            with open(CMD_FILE, 'w') as f:
                f.write(cmds[sel])
            xbmcgui.Dialog().notification('Quad DSP', f'Send: {cmds[sel]}', xbmcgui.NOTIFICATION_INFO, 1000)
        except Exception as e:
            xbmcgui.Dialog().ok("Error write", str(e))

if __name__ == '__main__':
    run()