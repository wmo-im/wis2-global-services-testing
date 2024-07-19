#! /usr/bin/python3
import paho.mqtt.client as mqtt
import ssl
import os,sys,time
from datetime import datetime
from time import sleep
import uuid
import queue
import threading

# Declaration
connected_flag = False
subscribed_flag = False
sub_error = ""
test_client = None
max_size_input_queue = 1000
input_queue = queue.Queue(maxsize=max_size_input_queue)
max_messages_test = 40
origin_messages_received = 0
stop_event = threading.Event()



def on_connect(client, userdata, flags, rc, properties=None):
    global connected_flag
    connected_flag = True


def on_disconnect(client, userdata, rc, properties=None):
    global connected_flag
    connected_flag = False


def on_subscribe(client, userdata, mid, reason_code_list, properties):
    global subscribed_flag
    global sub_error
    if reason_code_list[0].value == 1 or reason_code_list[0].value == 0:
        subscribed_flag = True
        print("-- Subscribed to topic, test messages should be published now")
    else:
        sub_error = "sub_error: " + reason_code_list[0].value


def on_mqtt_message(client, userdata, message):
    global input_queue
    global origin_messages_received
    global stop_event
    global connected_flag
    topic = ""
    msg_item = ""
    try:
        topic = message.topic
        msg_item = "".join([str(topic), ";", str(message.payload.decode("utf-8"))])
        try:
            if not stop_event.is_set():
                if origin_messages_received > max_messages_test:
                    if connected_flag is True:
                        stop_subscription()
                        print("-- STOP subscription - reached max_messages_test: " + str(max_messages_test))
                        stop_event.set()
                else:
                    # put to input_queue
                    input_queue.put(msg_item, timeout=2)
                    if "origin/a" in topic:
                        origin_messages_received = origin_messages_received + 1
        except Exception as on_mqtt_message_ex:
            print("".join([" - on_mqtt_message: on_mqtt_message_ex ", str(on_mqtt_message_ex)]))
    except Exception as e:
        print("".join([" - on_mqtt_message: topic - ", str(topic), ", message (", str(message.payload.decode("utf-8")), ")"]))
    # del
    del topic
    del msg_item


def get_tls_connection(mqtt_broker, mqtt_tls_port, clientname, mqtt_user, mqtt_password, sub_topic):
    test_client = mqtt.Client(clientname, protocol=mqtt.MQTTv5)
    test_client.username_pw_set(mqtt_user, password=mqtt_password)
    test_client.tls_set()
    test_client.on_connect = on_connect
    test_client.on_disconnect = on_disconnect
    test_client.on_subscribe = on_subscribe
    test_client.on_message = on_mqtt_message
    test_client.connect(mqtt_broker,int(mqtt_tls_port), properties=None)
    test_client.loop_start()
    return test_client

def connection_test(mqtt_broker, mqtt_tls_port, mqtt_user, mqtt_password, sub_topic):
    global connected_flag
    global sub_error
    connection_status = "NOT SET"
    subscribed_status = "NOT SET"
    error_message = ""
    # try to connect
    clientname = "wis2_test_"
    instanz_suffix = uuid.uuid1()
    clientname_instanz = clientname + str(instanz_suffix)
    test_client = get_tls_connection(mqtt_broker, mqtt_tls_port, clientname_instanz, mqtt_user, mqtt_password, sub_topic)
    sleep(1)
    if connected_flag:
        connection_status = "SUCCESS"
        test_client.subscribe(sub_topic, qos=1, options=None, properties=None)
        sleep(1)
        if subscribed_flag:
            subscribed_status = "SUCCESS"
        else:
            subscribed_status = "ERROR"
            error_message = sub_error
        test_client.disconnect()
        test_client.loop_stop()
    else:
        connection_status = "ERROR"
    return connection_status, subscribed_status, error_message


def start_subscription(mqtt_broker, mqtt_tls_port, mqtt_user, mqtt_password, sub_topic):
    global connected_flag
    global sub_error
    global test_client
    clientname = "wis2_test_"
    instanz_suffix = uuid.uuid1()
    clientname_instanz = clientname + str(instanz_suffix)
    connection_status = "NOT SET"
    subscribed_status = "NOT SET"
    error_message = ""
    # try to connect
    test_client = get_tls_connection(mqtt_broker, mqtt_tls_port, clientname_instanz, mqtt_user, mqtt_password, sub_topic)
    sleep(2)
    if connected_flag:
        connection_status = "SUCCESS"
        test_client.subscribe(sub_topic, qos=1, options=None, properties=None)
        sleep(2)
        if subscribed_flag:
            subscribed_status = "SUCCESS"
        else:
            subscribed_status = "ERROR"
            error_message = sub_error
    else:
        connection_status = "ERROR"
    return connection_status, subscribed_status, error_message


def stop_subscription():
    global test_client
    global connected_flag
    if not test_client is None:
        test_client.disconnect()
        test_client.loop_stop()
