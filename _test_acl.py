import paho.mqtt.client as mqtt
import time

received = []

def on_message(client, userdata, msg):
    received.append(msg.topic)
    print(f"Received: {msg.topic} = {msg.payload.decode()}")

def on_connect(client, userdata, flags, rc, *args):
    if rc == 0:
        client.subscribe("#", 2)
        time.sleep(0.5)
        client.publish("test/acl_check", "hello_acl", qos=0)

client = mqtt.Client()
client.username_pw_set("bunker", "bunker")
client.on_connect = on_connect
client.on_message = on_message
client.connect("localhost", 1900, 10)
client.loop_start()
time.sleep(3)
client.loop_stop()
print(f"Topics received: {received}")
