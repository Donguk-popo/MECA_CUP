import time

from managers.database_manager import DatabaseManager
from managers.camera_manager import CameraManager
from managers.plc_manager import PLCManager
from managers.rfid_manager import RFIDManager

class MasterController:
    def __init__(self):
        print("[Master] Init. . .")
        self.database = DatabaseManager()
        self.camera = CameraManager()
        self.plc = PLCManager()
        self.rfid = RFIDManager()
    def initialize(self):
        print("[Master] Initializing. . .")

    def connect_devices(self):
        print("[Master] Connecting Devices. . .")

        if not self.database.connect():
            print("[Master] Database connection failed.")
            return

        # PLC 연결
        if self.plc.connect():
            print("[Master] PLC Connected")
        else:
            print("[Master] PLC Connection Failed")


        # routes.py에 PLC 객체 전달
        from api.routes import set_plc_manager
        set_plc_manager(self.plc)

        # RFID 연결
        self.rfid.connect()

        # Camera 연결
        self.camera.connect()

    def run(self):
        print("[Master] System Running. . .")
        SYNC_EVERY_N_LOOPS = 60
        try:
            loop_count = 0
            while True:
                # PLC 데이터 읽기
                self.read_plc_and_save(["D100"])
                # RFID 체크
                epc = self.rfid.get_epc()
                if epc:
                    print(f"[Master] RFID detected : {epc}")
                    self.database.update_baggage_status_by_rfid(epc)
                  # 중복 RFID 방지
                    self.rfid.clear()

                loop_count += 1
                # Cloud Sync
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
    #     pass
    # def shutdown(self):
    #     pass