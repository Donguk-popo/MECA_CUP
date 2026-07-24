import json

import pymysql
import yaml
import paho.mqtt.client as mqtt

with open("config/config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

MQTT_CONF = config["mqtt"]
DB_CONF = config["database"]

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


def advance_status(rfid_tag):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, status FROM baggage WHERE rfid_tag = %s", (rfid_tag,))
            row = cursor.fetchone()

            if not row:
                print(f"[resp_test] no baggage found for rfid_tag={rfid_tag}")
                return

            baggage_id, current_status = row

            if current_status in STATUS_CYCLE:
                next_status = STATUS_CYCLE[(STATUS_CYCLE.index(current_status) + 1) % len(STATUS_CYCLE)]
            else:
                next_status = STATUS_CYCLE[0]

            cursor.execute("UPDATE baggage SET status = %s WHERE id = %s", (next_status, baggage_id))
            cursor.execute(
                "INSERT INTO event_log (baggage_id, event_type, message) VALUES (%s, %s, %s)",
                (baggage_id, next_status, "스위치 테스트로 상태 변경")
            )

        conn.commit()
        print(f"[resp_test] {rfid_tag}: {current_status} -> {next_status}")

    finally:
        conn.close()


def on_connect(client, userdata, flags, rc):
    print("[resp_test] MQTT Connected, rc =", rc)
    client.subscribe(MQTT_CONF["topic"])


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        print(f"[resp_test] invalid JSON payload: {msg.payload}")
        return

    print(f"[resp_test] received: {payload}")

    rfid_tag = payload.get("rfid_tag")
    value = payload.get("value")

    if value != 1 or not rfid_tag:
        return

    advance_status(rfid_tag)


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_CONF["broker"], MQTT_CONF["port"], 60)

    print("[resp_test] listening. . . (Ctrl+C to stop)")
    client.loop_forever()


if __name__ == "__main__":
    main()
