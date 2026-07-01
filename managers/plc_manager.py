import yaml
import pymcprotocol

class PLCManager:
    def __init__(self):
        print("[PLC] Init. . .")

        self.pymc = pymcprotocol.Type3E()
        self.connected = False

    def connect(self):
        print("[PLC] Connecting. . .")

        try:
            with open('config/config.yaml', 'r', encoding="utf-8") as f:
                config = yaml.safe_load(f)

            plc = config["plc"]

            self.pymc.connect(plc["ip"], plc["port"])
            self.connected = True

            print("[PLC] Connected")
            return True

        except Exception as e:
            print(f"[PLC] Connection Failed: {e}")
            self.connected = False
            return False

    def read_values(self, addresses):
        """addresses: list of word device address strings, e.g. ['D100', 'D101']
        returns dict {address: value}"""

        if not self.connected:
            print("[PLC] Not connected")
            return {}

        try:
            values = self.pymc.randomread(word_devices=addresses, dword_devices=[])
            return dict(zip(addresses, values[0]))

        except Exception as e:
            print(f"[PLC] Read Failed: {e}")
            return {}
