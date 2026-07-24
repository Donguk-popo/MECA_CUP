import json
import socket
import threading


class RFIDManager:
    def __init__(self,
                 host="0.0.0.0",
                 port=5050):

        print("[RFID] Init...")

        self.host = host
        self.port = port

        self.server = None
        self.stop_event = threading.Event()

        # 마지막으로 읽은 RFID
        self.current_epc = None

    def connect(self):
        """RFID TCP 서버 시작"""

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen()
        self.server.settimeout(1.0)

        print(f"[RFID] Listening : {self.host}:{self.port}")

        threading.Thread(
            target=self.accept_loop,
            daemon=True
        ).start()

    def accept_loop(self):

        while not self.stop_event.is_set():

            try:
                conn, addr = self.server.accept()

            except socket.timeout:
                continue

            print(f"[RFID] Connected : {addr}")

            threading.Thread(
                target=self.client_loop,
                args=(conn, addr),
                daemon=True
            ).start()

    def client_loop(self, conn, addr):

        buffer = ""

        with conn:

            conn.settimeout(1.0)

            while not self.stop_event.is_set():

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

                    try:
                        msg = json.loads(line)

                    except json.JSONDecodeError:
                        continue

                    if msg.get("type") != "rfid":
                        continue

                    epc = msg.get("epc")

                    if not epc:
                        continue

                    # 이전 RFID와 같으면 무시
                    if epc == self.current_epc:
                        continue

                    # 새로운 RFID
                    self.current_epc = epc

                    print(f"[RFID] {self.current_epc}")

        print(f"[RFID] Disconnected : {addr}")

    def get_epc(self):
        """현재 EPC 반환"""
        return self.current_epc

    def clear(self):
        """현재 EPC 초기화"""
        self.current_epc = None

    def disconnect(self):

        self.stop_event.set()

        if self.server:
            self.server.close()

        print("[RFID] Disconnect")