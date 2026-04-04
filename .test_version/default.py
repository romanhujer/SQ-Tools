#default.py
import xbmcgui
import xbmcaddon

addon = xbmcaddon.Addon()
dialog = xbmcgui.Dialog()

def show_menu():
    options = [
        "Režim: SQ (CBS)",
        "Režim: QS (Sansui)",
        "Režim: Stereo (Bypass)",
        "De-Clicker: ON/OFF",
        "Restartovat Audio Engine"
    ]
    
    choice = dialog.select("Kvadrofonní Procesor v7.5", options)
    
    if choice == 0:
        send_command("mode:sq")
    elif choice == 1:
        send_command("mode:qs")
    elif choice == 2:
        send_command("mode:stereo")
    elif choice == 3:
        send_command("toggle:filter")
    elif choice == 4:
        send_command("restart")

def send_command(cmd):
    # Zapíšeme příkaz do dočasného souboru, který náš engine čte
    with open("/tmp/quad_cmd", "w") as f:
        f.write(cmd)
    xbmcgui.Dialog().notification("Quad Proc", f"Příkaz odeslán: {cmd}", xbmcgui.NOTIFICATION_INFO, 2000)

if __name__ == '__main__':
    show_menu()