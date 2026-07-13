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
                        passenger_name VARCHAR(100) NOT NULL,
                        pnr_code VARCHAR(10),
                        e_ticket VARCHAR(20),
                        origin_iata CHAR(3),
                        dest_iata CHAR(3),
                        carrier_code CHAR(3),
                        flight_number VARCHAR(10),
                        flight_date DATE,
                        julian_date SMALLINT,
                        cabin_class CHAR(1),
                        seat_number VARCHAR(5),
                        checkin_seq SMALLINT,
                        passenger_status CHAR(1),
                        bcbp_raw VARCHAR(255),
                        baggage_tag VARCHAR(20),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS baggage (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        baggage_tag VARCHAR(20),
                        rfid_tag VARCHAR(32) UNIQUE,
                        qr_code VARCHAR(64) NULL,
                        owner_id BIGINT,
                        flight_no VARCHAR(10),
                        status VARCHAR(20) NOT NULL,
                        inspection_result VARCHAR(20),
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        delivered_at DATETIME NULL,
                        FOREIGN KEY (owner_id) REFERENCES passenger(id)
                    )
                """)

                cursor.execute(
                    """SELECT COUNT(*) FROM information_schema.statistics
                       WHERE table_schema = DATABASE() AND table_name = 'baggage' AND index_name = 'rfid_tag'"""
                )
                if cursor.fetchone()[0] == 0:
                    cursor.execute("ALTER TABLE baggage ADD UNIQUE (rfid_tag)")

                cursor.execute(
                    """SELECT COUNT(*) FROM information_schema.columns
                       WHERE table_schema = DATABASE() AND table_name = 'baggage' AND column_name = 'qr_code'"""
                )
                if cursor.fetchone()[0] == 0:
                    cursor.execute("ALTER TABLE baggage ADD COLUMN qr_code VARCHAR(64) NULL AFTER rfid_tag")

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
        from datetime import date

        with self.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM baggage")
            if cursor.fetchone()[0] > 0:
                print("[DB] Sample data already present, skipping seed")
                return

            flight_date = date(2026, 7, 9)
            julian_date = flight_date.timetuple().tm_yday

            # name, pnr_code, e_ticket, origin, dest, carrier, flight_number, cabin, seat, checkin_seq, passenger_status, bcbp_raw, baggage_tag
            passengers = [
                ("KIM/MINJUN", "ABCDEF", "1801234567890", "ICN", "NRT", "KE", "001", "Y", "12A", 1, "1", "M1KIM/MINJUN            EABCDEF ICNNRTKE 0001 190Y012A0001 15D", "KE0000001"),
                ("LEE/SEOYEON", "GHIJKL", "1801234567891", "ICN", "NRT", "KE", "002", "Y", "14C", 2, "1", "M1LEE/SEOYEON           EGHIJKL ICNNRTKE 0002 190Y014C0002 15D", "KE0000002"),
                ("PARK/DOYUN", "MNOPQR", "1801234567892", "ICN", "PUS", "OZ", "101", "Y", "05B", 3, "1", "M1PARK/DOYUN            EMNOPQR ICNPUSOZ 0101 190Y005B0003 15D", "OZ0000003"),
                ("CHOI/JIWOO", "STUVWX", "1801234567893", "ICN", "PUS", "OZ", "102", "C", "02A", 4, "1", "M1CHOI/JIWOO            ESTUVWX ICNPUSOZ 0102 190C002A0004 15D", "OZ0000004"),
                ("JUNG/HAYOON", "YZABCD", "1801234567894", "ICN", "CJU", "7C", "201", "Y", "20F", 5, "1", "M1JUNG/HAYOON           EYZABCD ICNCJU7C 0201 190Y020F0005 15D", "7C0000005"),
            ]
            cursor.executemany(
                """INSERT INTO passenger
                    (passenger_name, pnr_code, e_ticket, origin_iata, dest_iata, carrier_code,
                     flight_number, flight_date, julian_date, cabin_class, seat_number,
                     checkin_seq, passenger_status, bcbp_raw, baggage_tag)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [(p[0], p[1], p[2], p[3], p[4], p[5], p[6], flight_date, julian_date,
                  p[7], p[8], p[9], p[10], p[11], p[12]) for p in passengers]
            )

            # baggage_tag, rfid_tag, owner_id, flight_no, status, inspection_result, delivered_at
            baggages = [
                ("KE0000001", "RFID-001", 1, "KE001", "REGISTERED", "NORMAL", None),
                ("KE0000002", "RFID-002", 2, "KE002", "CIRCULATING", "NORMAL", None),
                ("OZ0000003", "RFID-003", 3, "OZ101", "READY", "NORMAL", None),
                ("OZ0000004", "RFID-004", 4, "OZ102", "DELIVERED", "NORMAL", "NOW()"),
                ("7C0000005", "RFID-005", 5, "7C201", "DEFECT", "DEFECT", None),
            ]
            for baggage_tag, rfid_tag, owner_id, flight_no, status, inspection_result, delivered_at in baggages:
                cursor.execute(
                    """
                    INSERT INTO baggage
                        (baggage_tag, rfid_tag, owner_id, flight_no, status, inspection_result, delivered_at)
                    VALUES (%s, %s, %s, %s, %s, %s, {})
                    """.format("NOW()" if delivered_at else "NULL"),
                    (baggage_tag, rfid_tag, owner_id, flight_no, status, inspection_result)
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