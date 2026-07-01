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