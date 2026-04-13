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
import xbmc


# Podporované dekodovací matrice
matrix = {
    "SQ"       : "SQ (CBS)",
    "QS"       : "QS (Sansui)",
    "MATRIXH"  : "Matrix H (BBC)",
    "STEREO4"  : "Stereo-4",
    "DOLBY"    : "Dolby Surround",
    "PL2"      : "Dolby Prologic II",
    "BYPASS"   : "Bypass 4:4", 
    "STEREO"   : "Stereo"
}   




class QuadControl(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        # Načtení dat předaných z funkce run()
        self.options = kwargs.get('options', [])
        self.cmds = kwargs.get('cmds', {})

    def onInit(self):
        # 1. Titulek (ID 1 v XML)
        self.getControl(1).setLabel(get_current_info())
        
        # 2. Seznam vlevo (ID 3 v XML)
        self.list_ctl = self.getControl(3)
        for item in self.options:
            self.list_ctl.addItem(xbmcgui.ListItem(item))
        
        # 3. Boční tlačítko START/STOP (ID 10 v XML)
        self.update_button_label()
        self.setFocus(self.list_ctl)

    def update_button_label(self):
        status = get_current_info()
        label = "STOP ENGINE" if "RUN" in status or "BĚŽÍ" in status else "START ENGINE"
        self.getControl(10).setLabel(label)

    def onClick(self, controlId):
        # Klik na boční tlačítko Start/Stop (ID 10)
        if controlId == 10:
            status = get_current_info()
            cmd = "dsp:stop" if "RUN" in status or "BĚŽÍ" in status else "dsp:start"
            self.send_cmd(cmd)
            
        # Klik na položku v seznamu (ID 3)
        elif controlId == 3:
            sel = self.list_ctl.getSelectedPosition()
            if sel in self.cmds:
                self.send_cmd(self.cmds[sel])

    def send_cmd(self, cmd):
        try:
            with open(CMD_FILE, 'w') as f:
                f.write(cmd)
            xbmc.sleep(600)
            self.close() # Zavře okno a v run() se díky loopu znovu otevře
        except:
            self.close()


def get_s(string_id):
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
                # Očekáváme formát z quadDSP.py: RUN|MODE|SR|BIT|FILTR|CENTER
                # s[0]=RUN/STOP, s[1]=MODE, s[2]=SR, s[3]=BIT, s[4]=ON/OFF, s[5]=ON/OFF
                filter_txt = get_s(30504) if s[4] == "ON" else ""
                center_txt = get_s(30503) if s[5] == "ON" else ""
                if s[0] == "RUN" :
                    status_txt =  get_s(30403)
                    info = f"{status_txt} : {matrix[s[1]]} ({s[2]}/{s[3]}) {center_txt} {filter_txt}"
                else:
                    info = get_s(30404)                                   
                return info
        except:
            pass
    offline_txt = get_s(30409)
    return f"[COLOR red]{offline_txt}[/COLOR]"

def run():
    dialog = xbmcgui.Dialog()
    if os.path.exists(STATUS_FILE):
        os.sync()
    # Definice položek menu
    options = [
        get_s(30401), # START
        get_s(30402), # STOP
        "--------------------------------",
        get_s(30001), # SQ (CBS)
        get_s(30002), # QS (Sansui)
        get_s(30003), # Matrix H (BBC)
        get_s(30004), # Stereo-4
        get_s(30005), # Dolby Stereo (Dolby Surround)
        get_s(30006), # Dolby Prologic II 
        get_s(30009), # Bypass
        get_s(30010), # Stereo
        "--------------------------------",
        get_s(30201), # 16bit
        get_s(30202), # 24bit
        "--------------------------------",
        get_s(30101), # 44.1k
        get_s(30102), # 48k
        get_s(30103), # 96k
        get_s(30104), # 192k
        "--------------------------------",
        get_s(30501), # Center Toggle
        get_s(30502), # De-clicker ON/OFF
    ]
    
    # Mapování příkazů na indexy v options
    cmds = {
        0: 'dsp:start',
        1: 'dsp:stop',
        3: 'mode:sq',
        4: 'mode:qs',
        5: 'mode:matrixh',
        6: 'mode:stereo4',
        7: 'mode:dolby', 
        8: 'mode:pl2',
        9: 'mode:bypass',
        10: 'mode:stereo',
        12: 'bit:16', # 16bit
        13: 'bit:24', # 24bit
        15: 'sr:44100', # 44.1k
        16: 'sr:48000', # 48k
        17: 'sr:96000', # 96k
        18: 'sr:192000', # 192k
        20: 'toggle:center', # centr
        21: 'toggle:filter'  # filter
    }
    bit_depth = ['bit:16', 'bit:24']
    sampling_rate = ['sr:44100','sr:48000','sr:96000','sr:192000' ] 
    #title = f"{get_s(30000)} {get_current_info()}"
    title = f"{get_current_info()}"
    sel = dialog.select(title, options)
    
    if sel >= 0:
        if sel in cmds:
            try:
                with open(CMD_FILE, 'w') as f:
                    f.write(cmds[sel])
                if cmds[sel] != 'dsp:stop' :
                    # Krátká pauza pro engine a refresh menu
                    xbmc.sleep(600)      
                    # Následujíc trvají déle zdůvodu restartu streamu v DSP
                    if  cmds[sel] in bit_depth or cmds[sel] in sampling_rate or cmds[sel] :
                        xbmc.sleep(2000)
                    run()    
            except Exception as e:
                xbmcgui.Dialog().ok("Error", str(e))
        else:
            # Kliknuto na oddělovač (---), prostě obnovíme menu
            run()

if __name__ == '__main__':
    run()



    import xbmcgui
import xbmcaddon
import os
import xbmc

# Definice souborů
STATUS_FILE = '/tmp/quad_status'
CMD_FILE = '/tmp/quad_cmd'

def get_s(string_id):
    try:
        return xbmcaddon.Addon().getLocalizedString(string_id)
    except:
        return str(string_id)

def get_current_info():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                s = f.read().strip().split('|')
                # s[0]=RUN/STOP, s[1]=MODE, s[2]=SR, s[3]=BIT
                status_txt = get_s(30403) if s[0] == "RUN" else get_s(30404)
                return f"{status_txt}: {s[1]} ({s[2]}/{s[3]})"
        except: pass
    return get_s(30409)


def run():
    addon = xbmcaddon.Addon()
    path = addon.getAddonInfo('path')
    
    # Definice obsahu (indexy musí sedět s tvým výběrem)
    options = [get_s(30001), get_s(30002), get_s(30003), get_s(30004), "---", get_s(30201), get_s(30202)]
    cmds = {0:'mode:sq', 1:'mode:qs', 2:'mode:matrixh', 3:'mode:stereo4', 5:'bit:16', 6:'bit:24'}

    # Spuštění XML okna
    # "Default", "720p" odpovídá složce resources/skins/Default/720p/
    wd = QuadControl("script-quad-control.xml", path, "Default", "720p", options=options, cmds=cmds)
    wd.doModal()
    del wd
    
    # Automatický refresh - pokud okno zavřeme příkazem, hned ho otevřeme s novým statusem
    # Pokud uživatel stiskne ESC/Back, skript skončí.
    # (Tady by mohl být cyklus, pokud bys chtěl menu držet otevřené)

if __name__ == '__main__':
    run()