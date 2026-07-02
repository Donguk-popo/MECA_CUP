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

    def sync_to_cloud(self):
        """Push local plc_log rows that haven't been synced yet to the cloud DB."""

        if not self.connection:
            print("[DB] Not connected")
            return False

        try:
            with open('config/config.yaml', 'r', encoding="utf-8") as f:
                config = yaml.safe_load(f)

            cloud_db = config["cloud_database"]

            with self.connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sync_state (
                        name VARCHAR(50) PRIMARY KEY,
                        last_id INT NOT NULL DEFAULT 0
                    )
                """)

                cursor.execute(
                    "SELECT last_id FROM sync_state WHERE name = %s", ("plc_log",)
                )
                row = cursor.fetchone()
                last_id = row[0] if row else 0

                cursor.execute(
                    "SELECT id, device, value, created_at FROM plc_log WHERE id > %s ORDER BY id",
                    (last_id,)
                )
                rows = cursor.fetchall()

            if not rows:
                return True

            cloud_connection = pymysql.connect(
                host=cloud_db["host"],
                port=cloud_db["port"],
                user=cloud_db["user"],
                password=cloud_db["password"],
                database=cloud_db["database"],
                charset="utf8mb4"
            )

            try:
                with cloud_connection.cursor() as cloud_cursor:
                    cloud_cursor.executemany(
                        "INSERT INTO plc_log (device, value, created_at) VALUES (%s, %s, %s)",
                        [(device, value, created_at) for _, device, value, created_at in rows]
                    )
                cloud_connection.commit()
            finally:
                cloud_connection.close()

            new_last_id = rows[-1][0]

            with self.connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO sync_state (name, last_id) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE last_id = %s",
                    ("plc_log", new_last_id, new_last_id)
                )
            self.connection.commit()

            print(f"[DB] Synced {len(rows)} rows to cloud")
            return True

        except Exception as e:
            print(f"[DB] Cloud Sync Failed: {e}")
            return False