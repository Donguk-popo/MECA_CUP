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

    def init_baggage_schema(self, seed_sample_data=True):
        """Create the baggage/passenger/event_log tables and, optionally,
        insert 5 sample rows into each (only if they're still empty)."""

        if not self.connection:
            print("[DB] Not connected")
            return False

        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS passenger (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        qr_code VARCHAR(64) NOT NULL UNIQUE,
                        phone VARCHAR(20),
                        flight_no VARCHAR(20),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS baggage (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        rfid_tag VARCHAR(32) NOT NULL UNIQUE,
                        owner_name VARCHAR(100) NOT NULL,
                        qr_code VARCHAR(64) NOT NULL,
                        flight_no VARCHAR(20) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        segment INT NULL,
                        discharge_point INT NULL,
                        inspection_result VARCHAR(20),
                        registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        delivered_at DATETIME NULL,
                        remark VARCHAR(255)
                    )
                """)

                for column, ddl in (
                    ("segment", "ALTER TABLE baggage ADD COLUMN segment INT NULL AFTER status"),
                    ("discharge_point", "ALTER TABLE baggage ADD COLUMN discharge_point INT NULL AFTER segment"),
                ):
                    cursor.execute(
                        """SELECT COUNT(*) FROM information_schema.columns
                           WHERE table_schema = DATABASE() AND table_name = 'baggage' AND column_name = %s""",
                        (column,)
                    )
                    if cursor.fetchone()[0] == 0:
                        cursor.execute(ddl)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS event_log (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        baggage_id BIGINT NOT NULL,
                        event_type VARCHAR(30) NOT NULL,
                        message VARCHAR(255),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (baggage_id) REFERENCES baggage(id)
                    )
                """)

            self.connection.commit()
            print("[DB] baggage/passenger/event_log schema ready")

            if seed_sample_data:
                self._seed_baggage_sample_data()

            return True

        except Exception as e:
            print(f"[DB] Schema Init Failed: {e}")
            return False

    def _seed_baggage_sample_data(self):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM baggage")
            if cursor.fetchone()[0] > 0:
                print("[DB] Sample data already present, skipping seed")
                return

            passengers = [
                ("김민준", "QR-0001", "010-1111-1111", "KE001"),
                ("이서연", "QR-0002", "010-2222-2222", "KE002"),
                ("박도윤", "QR-0003", "010-3333-3333", "OZ101"),
                ("최지우", "QR-0004", "010-4444-4444", "OZ102"),
                ("정하윤", "QR-0005", "010-5555-5555", "7C201"),
            ]
            cursor.executemany(
                "INSERT INTO passenger (name, qr_code, phone, flight_no) VALUES (%s, %s, %s, %s)",
                passengers
            )

            baggages = [
                ("RFID-001", "김민준", "QR-0001", "KE001", "REGISTERED", None, None, "NORMAL", None, None),
                ("RFID-002", "이서연", "QR-0002", "KE002", "CIRCULATING", 3, None, "NORMAL", None, None),
                ("RFID-003", "박도윤", "QR-0003", "OZ101", "READY", None, 7, "NORMAL", None, None),
                ("RFID-004", "최지우", "QR-0004", "OZ102", "DELIVERED", None, None, "NORMAL", "NOW()", None),
                ("RFID-005", "정하윤", "QR-0005", "7C201", "DEFECT", None, None, "DEFECT", None, "표면 손상 확인됨"),
            ]
            for rfid_tag, owner_name, qr_code, flight_no, status, segment, discharge_point, inspection_result, delivered_at, remark in baggages:
                cursor.execute(
                    """
                    INSERT INTO baggage
                        (rfid_tag, owner_name, qr_code, flight_no, status, segment, discharge_point, inspection_result, delivered_at, remark)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, {}, %s)
                    """.format("NOW()" if delivered_at else "NULL"),
                    (rfid_tag, owner_name, qr_code, flight_no, status, segment, discharge_point, inspection_result, remark)
                )

            events = [
                (1, "REGISTERED", "RFID 태그 인식 및 캐리어 등록 완료"),
                (2, "CIRCULATING", "컨베이어 순환 중"),
                (3, "READY", "배출 준비 완료"),
                (4, "DELIVERED", "승객 수령 완료"),
                (5, "DEFECT", "AI 비전 검사 결과 불량 판정"),
            ]
            cursor.executemany(
                "INSERT INTO event_log (baggage_id, event_type, message) VALUES (%s, %s, %s)",
                events
            )

        self.connection.commit()
        print("[DB] Seeded 5 sample rows into baggage/passenger/event_log")

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

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS plc_log (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        device VARCHAR(20) NOT NULL,
                        value INT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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