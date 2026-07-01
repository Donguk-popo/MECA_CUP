import yaml
import pymysql

class DatabaseManager:
    def __init__(self):
        print("[DB] Init. . .")

        self.connection = None

    def connect(self):

        try:
            with open('config/config.yaml', 'r',encoding="utf-8") as f:
                config = yaml.safe_load(f)

            db = config["database"]

            self.connection = pymysql.connect(
                host=db["host"],
                port=db["port"],
                user=db["user"],
                password=db["password"],
                database=db["database"],
                charset="utf8mb4"
            )

            print("[DB] Connected")
            return True
        
        except Exception as e:
            print(f"[DB] Connection Failed: {e}")
            return False

    def save_plc_data(self, readings):
        """readings: dict {device_address: value}"""

        if not self.connection:
            print("[DB] Not connected")
            return False

        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS plc_log (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        device VARCHAR(20) NOT NULL,
                        value INT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                for device, value in readings.items():
                    cursor.execute(
                        "INSERT INTO plc_log (device, value) VALUES (%s, %s)",
                        (device, value)
                    )

            self.connection.commit()
            print(f"[DB] Saved PLC data: {readings}")
            return True

        except Exception as e:
            print(f"[DB] Save Failed: {e}")
            return False