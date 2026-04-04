import sounddevice as sd

def debug_audio():
    print("\n" + "="*50)
    print("--- DETAILNÍ SCAN AUDIO HARDWARU ---")
    print("="*50)
    
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        print(f"\nINDEX [{i}]: {d['name']}")
        print(f"  Max In:  {d['max_input_channels']}")
        print(f"  Max Out: {d['max_output_channels']}")
        print(f"  Default SampleRate: {d['default_samplerate']}")
        # Host API info
        hostapi = sd.query_hostapis(d['hostapi'])
        print(f"  API: {hostapi['name']}")

    print("\n" + "="*50)
    print("--- TEST KONKRÉTNÍCH HW ADRES ---")
    
    # Zkusíme zjistit detaily pro tvé HW adresy
    for hw in ['hw:2,0', 'hw:0,0', 'hw:1,0']:
        try:
            info = sd.query_devices(hw)
            print(f"\nADRESA '{hw}':")
            print(f"  Jméno: {info['name']}")
            print(f"  Kanály: In={info['max_input_channels']}, Out={info['max_output_channels']}")
        except Exception as e:
            print(f"\nADRESA '{hw}': NENÍ DOSTUPNÁ ({e})")

if __name__ == "__main__":
    debug_audio()
    