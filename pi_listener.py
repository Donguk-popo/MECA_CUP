import json
import socket

import pymysql
import yaml

with open("config/config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

DB_CONF = config["database"]
CLOUD_DB_CONF = config["cloud_database"]

HOST = "0.0.0.0"  # 192.168.3.41(이더넷) 등 모든 인터페이스에서 연결을 받음
PORT = 9000

# 스위치를 누를 때마다 다음 상태로 순환
STATUS_CYCLE = ["REGISTERED", "CIRCULATING", "READY", "DELIVERED"]


def get_connection():
    return pymysql.connect(
        host=DB_CONF["host"],
        port=DB_CONF["port"],
        user=DB_CONF["user"],
        password=DB_CONF["password"],
        database=DB_CONF["database"],
        charset="utf8mb4"
    )


def get_cloud_connection():
    return pymysql.connect(
        host=CLOUD_DB_CONF["host"],
        port=CLOUD_DB_CONF["port"],
        user=CLOUD_DB_CONF["user"],
        password=CLOUD_DB_CONF["password"],
        database=CLOUD_DB_CONF["database"],
        charset="utf8mb4"
    )


def update_cloud_status(rfid_tag, next_status):
    try:
        conn = get_cloud_connection()
    except Exception as e:
        print(f"[pi_listener] cloud connect failed: {e}")
        return

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM baggage WHERE rfid_tag = %s", (rfid_tag,))
            row = cursor.fetchone()

            if not row:
                print(f"[pi_listener] cloud: no baggage found for rfid_tag={rfid_tag}")
                return

            baggage_id = row[0]

            cursor.execute("UPDATE baggage SET status = %s WHERE id = %s", (next_status, baggage_id))
            cursor.execute(
                "INSERT INTO event_log (baggage_id, event_type, message) VALUES (%s, %s, %s)",
                (baggage_id, next_status, "라즈베리파이 스위치로 상태 변경")
            )

        conn.commit()
        print(f"[pi_listener] cloud updated: {rfid_tag} -> {next_status}")

    except Exception as e:
        print(f"[pi_listener] cloud update failed: {e}")

    finally:
        conn.close()


def advance_status(rfid_tag):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, status FROM baggage WHERE rfid_tag = %s", (rfid_tag,))
            row = cursor.fetchone()

            if not row:
                print(f"[pi_listener] no baggage found for rfid_tag={rfid_tag}")
                return

            baggage_id, current_status = row

            if current_status in STATUS_CYCLE:
                next_status = STATUS_CYCLE[(STATUS_CYCLE.index(current_status) + 1) % len(STATUS_CYCLE)]
            else:
                next_status = STATUS_CYCLE[0]

            cursor.execute("UPDATE baggage SET status = %s WHERE id = %s", (next_status, baggage_id))
            cursor.execute(
                "INSERT INTO event_log (baggage_id, event_type, message) VALUES (%s, %s, %s)",
                (baggage_id, next_status, "라즈베리파이 스위치로 상태 변경")
            )

        conn.commit()
        print(f"[pi_listener] {rfid_tag}: {current_status} -> {next_status}")

    finally:
        conn.close()

    update_cloud_status(rfid_tag, next_status)


def handle_client(conn, addr):
    print(f"[pi_listener] connected: {addr}")
    buffer = ""

    with conn:
        while True:
            data = conn.recv(1024)
            if not data:
                break

            buffer += data.decode("utf-8", errors="ignore")

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    print(f"[pi_listener] invalid JSON: {line}")
                    continue

                print(f"[pi_listener] received: {payload}")

                rfid_tag = payload.get("rfid_tag")
                value = payload.get("value")

                if value == 1 and rfid_tag:
                    advance_status(rfid_tag)

    print(f"[pi_listener] disconnected: {addr}")


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()

    print(f"[pi_listener] listening on {HOST}:{PORT}. . . (Ctrl+C to stop)")

    try:
        while True:
            conn, addr = server.accept()
            handle_client(conn, addr)
    except KeyboardInterrupt:
        print("[pi_listener] stopped")
    finally:
        server.close()


if __name__ == "__main__":
    main()
