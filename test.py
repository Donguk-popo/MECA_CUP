import json
import os
import socket
import threading
from datetime import datetime

import cv2
import imagezmq

SAVE_DIR = r"C:\MECA_CUP\img_data"
os.makedirs(SAVE_DIR, exist_ok=True)

RFID_HOST = "0.0.0.0"
RFID_PORT = 5050  # 5000은 이 PC에서 Windows(HelpDocumentationViewer)가 이미 점유 중
RFID_LOG_PATH = r"C:\MECA_CUP\rfid_stream.log"

stop = threading.Event()


# ---------- RFID (raw TCP, 로그만) ----------
def rfid_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((RFID_HOST, RFID_PORT))
    server.listen()
    server.settimeout(1.0)  # stop 이벤트를 주기적으로 확인하기 위한 논블로킹 accept
    print(f"[RFID] listening on {RFID_HOST}:{RFID_PORT}")

    while not stop.is_set():
        try:
            conn, addr = server.accept()
        except socket.timeout:
            continue

        threading.Thread(target=handle_rfid_client, args=(conn, addr), daemon=True).start()

    server.close()


def handle_rfid_client(conn, addr):
    print(f"[RFID] connected: {addr}")
    buffer = ""

    with conn, open(RFID_LOG_PATH, "a", encoding="utf-8") as log_file:
        conn.settimeout(1.0)
        while not stop.is_set():
            try:
                data = conn.recv(1024)
            except socket.timeout:
                continue
            except OSError:
                break

            if not data:
                break

            buffer += data.decode("utf-8", errors="ignore")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                print(f"[RFID] {line}")
                log_file.write(f"{datetime.now().isoformat(timespec='milliseconds')} {line}\n")
                log_file.flush()

    print(f"[RFID] disconnected: {addr}")


# ---------- 카메라 (imagezmq, REQ/REP라 자체적으로 백프레셔 걸림) ----------
def camera_loop():
    receiver = imagezmq.ImageHub(open_port="tcp://*:5555")
    print("[CAM] 대기 중... (s: 저장 / q: 종료)")

    try:
        while True:
            msg, frame = receiver.recv_image()
            receiver.send_reply(b"OK")

            try:
                meta = json.loads(msg)
                hostname = meta.get("host", "unknown")
                epc = meta.get("epc")
            except (json.JSONDecodeError, TypeError):
                hostname = msg
                epc = None

            display_frame = frame
            if epc:
                # print(epc)
                display_frame = frame.copy()
                cv2.putText(display_frame, f"EPC: {epc}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow(f"Pi Camera [{hostname}]", display_frame)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("s"):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                suffix = f"_{epc}" if epc else ""
                filename = os.path.join(SAVE_DIR, f"capture_{timestamp}{suffix}.jpg")
                cv2.imwrite(filename, frame)
                print(f"저장 완료 → {filename}")

            elif key == ord("q"):
                print("종료")
                break

    finally:
        cv2.destroyAllWindows()
        receiver.zmq_socket.close()


if __name__ == "__main__":
    threading.Thread(target=rfid_server, daemon=True).start()

    try:
        camera_loop()
    finally:
        stop.set()