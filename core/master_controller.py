import time

from managers.database_manager import DatabaseManager
from managers.app_manager import AppManager
from managers.rasp_manager import RaspManager
from managers.plc_manager import PLCManager
from managers.rfid_manager import RFIDManager

class MasterController:
    def __init__(self):
        print("[Master] Init. . .")

        self.database = DatabaseManager()
        self.app = AppManager()
        self.rasp = RaspManager()
        self.plc = PLCManager()
        self.rfid = RFIDManager()

    def initialize(self):
        print("[Master] Initializing. . .")

    def connect_devices(self):
        print("[Master] Connecting Devices. . .")

        if not self.database.connect():
            print("[Master] Database connection failed.")
            return
        
        self.app.connect()
        self.rasp.connect()
        self.plc.connect()
        self.rfid.connect()

    def run(self):
        print("[Master] System Running. . .")

        SYNC_EVERY_N_LOOPS = 60  # 1 loop = 1 sec, so 60 loops = 1 min

        try:
            loop_count = 0
            while True:
                self.read_plc_and_save(["D100"])

                loop_count += 1
                if loop_count % SYNC_EVERY_N_LOOPS == 0:
                    self.database.sync_to_cloud()

                time.sleep(1)
        except KeyboardInterrupt:
            print("[Master] Stopped by user.")

    def read_plc_and_save(self, addresses):
        readings = self.plc.read_values(addresses)

        if not readings:
            return False

        return self.database.save_plc_data(readings)

    def start(self):
        print("[Master] Starting. . .")
        self.initialize()
        self.connect_devices()
        self.run()

    # def emergency_stop(self):
    #    pass
    
    # def shutdown(self):
    #    pass
