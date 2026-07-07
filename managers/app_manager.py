
import json
import yaml
import paho.mqtt.client as mqtt


class AppManager:

    def __init__(self):
        print("[App] Init...")

        self.client = mqtt.Client()

        with open("config/config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self.mqtt = config["mqtt"]

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def connect(self):
        print("[App] Connecting...")

        try:
            result = self.client.connect(
                self.mqtt["broker"],
                self.mqtt["port"],
                60
            )

            print("[App] connect() result =", result)

        except Exception as e:
            print("[MQTT CONNECT ERROR]", e)


    def start(self):
        print("[App] MQTT Listening...")
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, rc):
        print("[App] MQTT Connected")

        client.subscribe(self.mqtt["topic"])

    def on_message(self, client, userdata, msg):

        data = msg.payload.decode()

        print(f"[APP] Receive : {data}")

        # TODO :
        # MasterController에게 전달

    def publish(self, topic, message):

        self.client.publish(
            topic,
            json.dumps(message)
        )

    def disconnect(self):

        self.client.loop_stop()

        self.client.disconnect()

        print("[App] Disconnected")
