import json
import uuid
import copy
import random
import sys
import ssl
import os
import re

import pytest
import paho.mqtt.client as mqtt
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from dotenv import load_dotenv

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared_utils import ab, prom_metrics

# Connection strings for the development global broker and message generator
# Access the environment variables
load_dotenv("./global-broker.env")
load_dotenv("../secrets.env")
load_dotenv("../default.env")
mqtt_broker_trigger = os.getenv('TRIGGER_BROKER')
mqtt_broker_clear = os.getenv('TEST_GB_MQTT_BROKER')
mqtt_broker_tls = os.getenv('TEST_GB_MQTT_SSL_BROKER')
mqtt_broker_ws = os.getenv('TEST_GB_MQTT_WS_BROKER')
mqtt_broker_test = os.getenv('TEST_GB_MQTT_TEST_BROKER')

# prometheus config
prom_host = os.getenv('PROMETHEUS_HOST')
prom_user = os.getenv('PROMETHEUS_USER')
prom_pass = os.getenv('PROMETHEUS_PASSWORD')

# timing config
test_pace = float(os.getenv('TEST_PACE'))
message_pace = float(os.getenv('MESSAGE_PACE'))

# Test Centre IDs
MQTTX_CENTRE_ID_MIN = 1000
MQTTX_CENTRE_ID_MAX = 1004
WNMBENCH_CENTRE_ID_MIN = 100
WNMBENCH_CENTRE_ID_MAX = 299

# Connections
broker_tls_connections = [
    mqtt_broker_tls,
    mqtt_broker_ws
]

# Global Topics
sub_global_topics = [
    "origin/a/wis2/#",
    "cache/a/wis2/#"
]

# Node Topics
# dynamically generate sub_result_topics based on centre IDs
sub_result_topics = [f"result/a/wis2/io-wis2dev-{i:04d}-test/#" for i in range(MQTTX_CENTRE_ID_MIN, MQTTX_CENTRE_ID_MAX + 1)]

low_perf_settings = [
        {"mqttx_concurrent" : 8, "mqttx_tmout": 20, "msg_count": 2, "msg_delay": 500},
        {"mqttx_concurrent" : 8, "mqttx_tmout": 20, "msg_count": 4, "msg_delay": 500},
        {"mqttx_concurrent" : 8, "mqttx_tmout": 20, "msg_count": 6, "msg_delay": 500},
        {"mqttx_concurrent" : 8, "mqttx_tmout": 40, "msg_count": 8, "msg_delay": 500},
        {"mqttx_concurrent" : 8, "mqttx_tmout": 40, "msg_count": 10, "msg_delay": 500},
        {"mqttx_concurrent" : 8, "mqttx_tmout": 40, "msg_count": 12, "msg_delay": 500}
        ]

med_perf_settings = [
        {"mqttx_concurrent" : 4, "mqttx_tmout": 20, "msg_count": 4, "msg_delay": 100},
        {"mqttx_concurrent" : 8, "mqttx_tmout": 20, "msg_count": 8, "msg_delay": 100},
        {"mqttx_concurrent" : 16, "mqttx_tmout": 40, "msg_count": 16, "msg_delay": 100},
        {"mqttx_concurrent" : 32, "mqttx_tmout": 40, "msg_count": 32, "msg_delay": 100}
        ]

high_perf_settings = [
        {"mqttx_concurrent" : 8, "mqttx_tmout": 30, "msg_count": 8, "msg_delay": 50},
        {"mqttx_concurrent" : 16, "mqttx_tmout": 30, "msg_count": 16, "msg_delay": 50},
        {"mqttx_concurrent" : 32, "mqttx_tmout": 60, "msg_count": 32, "msg_delay": 50},
        {"mqttx_concurrent" : 64, "mqttx_tmout": 90, "msg_count": 64, "msg_delay": 50}
        ]

extreme_perf_settings = [
        {"mqttx_concurrent" : 16, "mqttx_tmout": 30, "msg_count": 16, "msg_delay": 20},
        {"mqttx_concurrent" : 32, "mqttx_tmout": 60, "msg_count": 32, "msg_delay": 20},
        {"mqttx_concurrent" : 64, "mqttx_tmout": 90, "msg_count": 64, "msg_delay": 20},
        {"mqttx_concurrent" : 128, "mqttx_tmout": 120, "msg_count": 128, "msg_delay": 20},
        ]

heroic_perf_settings = [
        {"mqttx_concurrent" : 32, "mqttx_tmout": 60, "msg_count": 32, "msg_delay": 5},
        {"mqttx_concurrent" : 64, "mqttx_tmout": 90, "msg_count": 64, "msg_delay": 5},
        {"mqttx_concurrent" : 128, "mqttx_tmout": 120, "msg_count": 128, "msg_delay": 5},
        {"mqttx_concurrent" : 256, "mqttx_tmout": 160, "msg_count": 256, "msg_delay": 5},
        ]

center_id_regex = re.compile(r"io-wis2dev-([0-9]{2})-test")
result_count_regex = re.compile(r"Received total:\s([0-9]+),\srate:\s[0-9]+/s")
#result_count_regex = re.compile(r"Received total:\s([0-9]+),\srate:.*\s[0-9]+/s")

def flag_on_connect(client, userdata, flags, rc, properties=None):
#    print(rc)
    client.connected_flag = True

def flag_on_subscribe(client, userdata, mid, granted_qos, properties=None):
#    print("Subscribed with mid " + str(mid) + " and QoS " + str(granted_qos[0]))
    client.subscribed_flag = True

def flag_on_message(client, userdata, msg):
#    print(f"Received message on topic {msg.topic} with payload {msg.payload}")
    try:
        msg_json = json.loads(msg.payload)
    except:
        msg_json = {'payload': re.sub(r'[^\x00-\x7F]','',msg.payload.decode())}
    msg_json['topic'] = msg.topic
    client._userdata['received_messages'].append(msg_json)
    client.message_flag = True

def wait_for_results(sub_client, max_wait_time=10, min_wait_time=0):
    elapsed_time = 0
    while elapsed_time < max_wait_time:
        recv_msgs = sub_client._userdata['received_messages']
#        print(f"Results received: {len(recv_msgs)} ... {len(sub_result_topics)}")
        if len(recv_msgs) == len(sub_result_topics):
#            print(f"Results received within {elapsed_time} seconds.")
            break
        time.sleep(message_pace)
        elapsed_time += message_pace
    for result_mesg in recv_msgs:
        counts = []
        lastline = result_mesg['payload'].splitlines()[-1]
        result_mesg['max_recv'] = result_count_regex.search(lastline).group(1)
    return recv_msgs


#def get_gc_metrics(prometheus_baseurl, username, password, centre_id=None):
#    """
#    Fetches GC metrics from Prometheus.
#
#    Args:
#        prometheus_baseurl (str): The base URL of the Prometheus server.
#        username (str): The username for Prometheus authentication.
#        password (str): The password for Prometheus authentication.
#        centre_id (str): The centre ID to filter the metrics by.
#
#    Returns:
#        dict: A dictionary containing the fetched metrics.
#    """
#    print("Fetching GC Metrics")
#    report_by = os.getenv('GC_METRICS_REPORT_BY')
#    if centre_id is not None:
#        centre_id = f'io-wis2dev-{centre_id}-test'
#    print(f"Report by: {report_by}")
#    metrics_to_fetch = [
#        "wmo_wis2_gb_messages_published_total",
#        "wmo_wis2_gb_messages_received_total",
#        "wmo_wis2_gb_messages_no_metadata_total",
#        "wmo_wis2_gb_last_message_timestamp_seconds",
#        "wmo_wis2_gb_connected_flag"
#    ]
#
#    metrics = {}
#    for metric_name in metrics_to_fetch:
#        result = fetch_prometheus_metrics(metric_name, prometheus_baseurl, username, password, report_by=report_by,
#                                          centre_id=centre_id)
#        metrics[metric_name] = result
#    return metrics

def setup_mqtt_client(connection_info: str, verify_cert: bool):
    rand_id = "TEST-mqttx-" + str(uuid.uuid4())[:10]
    connection_info = urlparse(connection_info)
    if connection_info.scheme in ['ws', 'wss']:
        client = mqtt.Client(client_id=rand_id, transport='websockets', protocol=mqtt.MQTTv5, userdata={'received_messages': []})
    else:
        client = mqtt.Client(client_id=rand_id, transport='tcp', protocol=mqtt.MQTTv5, userdata={'received_messages': []})
    client.on_connect = flag_on_connect
    client.on_subscribe = flag_on_subscribe
    client.on_message = flag_on_message
    client.username_pw_set(connection_info.username, connection_info.password)
    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = 300  # seconds
    if connection_info.port in [443, 8883]:
        tls_settings = { 'tls_version': 2 }
        if not verify_cert:
            tls_settings['cert_reqs'] = ssl.CERT_NONE
        client.tls_set(**tls_settings)
    try:
        client.connect(host=connection_info.hostname, port=connection_info.port, properties=properties)
        client.loop_start()
        time.sleep(message_pace)  # Wait for connection
        if not client.is_connected() and loop_start:
            raise Exception("Failed to connect to MQTT broker")
    except Exception as e:
        print(f"Connection error: {e}")
        print(f"Parsed connection string components:")
        print(f"  Scheme: {connection_info.scheme}")
        print(f"  Hostname: {connection_info.hostname}")
        print(f"  Port: {connection_info.port}")
        print(f"  Username: {connection_info.username}")
        print(f"  Password: {connection_info.password}")
        raise
    return client

@pytest.mark.parametrize("perf_set", low_perf_settings)
def test_1_mqtt_broker_lowperf(perf_set):
    print("\n1. WIS2 Broker LOW Performance Test")
    print(f"MQTTx Concurrent: {perf_set['mqttx_concurrent']}  MQTTx Timeout: {perf_set['mqttx_tmout']}  Message Count: {perf_set['msg_count']}  Message Delay: {perf_set['msg_delay']}")
    sub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    sub_client.subscribe("result/a/wis2/#", qos=1)
    time.sleep(message_pace)  # Wait for subscription
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    broker_info = urlparse(mqtt_broker_test)
    mqttx_scenario_start = {
        "scenario": "mqttx",
        "configuration": {
            "setup": {
                "centreid_min": MQTTX_CENTRE_ID_MIN,
                "centreid_max": MQTTX_CENTRE_ID_MAX,
                "timeout": perf_set['mqttx_tmout'],
                "concurrent": perf_set['mqttx_concurrent'],
                "username": broker_info.username,
                "password": broker_info.password,
                "broker": f"{broker_info.scheme}://{broker_info.hostname}",
                "port": broker_info.port,
                "action": "start",
                "topic": "origin/a/wis2/#"
            }
        }
    }
    mqttx_scenario_stop = {
        "scenario": "mqttx",
        "configuration": {
            "setup": {
                "centreid_min": MQTTX_CENTRE_ID_MIN,
                "centreid_max": MQTTX_CENTRE_ID_MAX,
                "action": "stop",
            }
        }
    }
    wnmbench_scenario_config = {
        "scenario": "wnmbench",
        "configuration": {
            "setup": {
                "centreid_min": WNMBENCH_CENTRE_ID_MIN,
                "centreid_max": WNMBENCH_CENTRE_ID_MAX,
                "number": perf_set['msg_count'],
                "delay": perf_set['msg_delay']
            }
        }
    }
#    print(f"Scenario message: {json.dumps(mqttx_scenario_start, indent=4)}")
    pub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    assert pub_client.connected_flag
    pub_client.publish("config/a/wis2", json.dumps(mqttx_scenario_start))
    time.sleep((perf_set['mqttx_concurrent']*0.2)+5)  # Wait for publish
#    print(f"Scenario message: {json.dumps(wnmbench_scenario_config, indent=4)}")
    sub_client.publish("config/a/wis2", json.dumps(wnmbench_scenario_config))
    time.sleep(message_pace)  # Wait for publish

    result_msgs = wait_for_results(sub_client, perf_set['mqttx_tmout'] + 10, perf_set['mqttx_tmout'])
    assert len(result_msgs) == len(sub_result_topics)
    for mesg_count in result_msgs:
        print(f"MQTTx Client: {mesg_count['topic'].split('/')[3]}    Total Received: {mesg_count['max_recv']}    Expected: {200 * perf_set['msg_count'] * perf_set['mqttx_concurrent']}")
    sub_client.loop_stop()
    sub_client.disconnect()
    del sub_client
    time.sleep(test_pace)


@pytest.mark.parametrize("perf_set", med_perf_settings)
def test_2_mqtt_broker_medperf(perf_set):
    print("\n2. WIS2 Broker MEDIUM Performance Test")
    print(f"MQTTx Concurrent: {perf_set['mqttx_concurrent']}  MQTTx Timeout: {perf_set['mqttx_tmout']}  Message Count: {perf_set['msg_count']}  Message Delay: {perf_set['msg_delay']}")
    sub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    sub_client.subscribe("result/a/wis2/#", qos=1)
    time.sleep(message_pace)  # Wait for subscription
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    broker_info = urlparse(mqtt_broker_test)
    mqttx_scenario_start = {
        "scenario": "mqttx",
        "configuration": {
            "setup": {
                "centreid_min": MQTTX_CENTRE_ID_MIN,
                "centreid_max": MQTTX_CENTRE_ID_MAX,
                "timeout": perf_set['mqttx_tmout'],
                "concurrent": perf_set['mqttx_concurrent'],
                "username": broker_info.username,
                "password": broker_info.password,
                "broker": f"{broker_info.scheme}://{broker_info.hostname}",
                "port": broker_info.port,
                "action": "start",
                "topic": "origin/a/wis2/#"
            }
        }
    }
    mqttx_scenario_stop = {
        "scenario": "mqttx",
        "configuration": {
            "setup": {
                "centreid_min": MQTTX_CENTRE_ID_MIN,
                "centreid_max": MQTTX_CENTRE_ID_MAX,
                "action": "stop",
            }
        }
    }
    wnmbench_scenario_config = {
        "scenario": "wnmbench",
        "configuration": {
            "setup": {
                "centreid_min": WNMBENCH_CENTRE_ID_MIN,
                "centreid_max": WNMBENCH_CENTRE_ID_MAX,
                "number": perf_set['msg_count'],
                "delay": perf_set['msg_delay']
            }
        }
    }
#    print(f"Scenario message: {json.dumps(mqttx_scenario_start, indent=4)}")
    pub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    assert pub_client.connected_flag
    pub_client.publish("config/a/wis2", json.dumps(mqttx_scenario_start))
    time.sleep((perf_set['mqttx_concurrent']*0.2)+5)  # Wait for publish
#    print(f"Scenario message: {json.dumps(wnmbench_scenario_config, indent=4)}")
    sub_client.publish("config/a/wis2", json.dumps(wnmbench_scenario_config))
    time.sleep(message_pace)  # Wait for publish

    result_msgs = wait_for_results(sub_client, perf_set['mqttx_tmout'] + 10, perf_set['mqttx_tmout'])
    assert len(result_msgs) == len(sub_result_topics)
    for mesg_count in result_msgs:
        print(f"MQTTx Client: {mesg_count['topic'].split('/')[3]}    Total Received: {mesg_count['max_recv']}    Expected: {200 * perf_set['msg_count'] * perf_set['mqttx_concurrent']}")
    sub_client.loop_stop()
    sub_client.disconnect()
    del sub_client
    time.sleep(test_pace)

@pytest.mark.parametrize("perf_set", high_perf_settings)
def test_3_mqtt_broker_highperf(perf_set):
    print("\n3. WIS2 Broker HIGH Performance Test")
    print(f"MQTTx Concurrent: {perf_set['mqttx_concurrent']}  MQTTx Timeout: {perf_set['mqttx_tmout']}  Message Count: {perf_set['msg_count']}  Message Delay: {perf_set['msg_delay']}")
    sub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    sub_client.subscribe("result/a/wis2/#", qos=1)
    time.sleep(message_pace)  # Wait for subscription
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    broker_info = urlparse(mqtt_broker_test)
    mqttx_scenario_start = {
        "scenario": "mqttx",
        "configuration": {
            "setup": {
                "centreid_min": MQTTX_CENTRE_ID_MIN,
                "centreid_max": MQTTX_CENTRE_ID_MAX,
                "timeout": perf_set['mqttx_tmout'],
                "concurrent": perf_set['mqttx_concurrent'],
                "username": broker_info.username,
                "password": broker_info.password,
                "broker": f"{broker_info.scheme}://{broker_info.hostname}",
                "port": broker_info.port,
                "action": "start",
                "topic": "origin/a/wis2/#"
            }
        }
    }
    mqttx_scenario_stop = {
        "scenario": "mqttx",
        "configuration": {
            "setup": {
                "centreid_min": MQTTX_CENTRE_ID_MIN,
                "centreid_max": MQTTX_CENTRE_ID_MAX,
                "action": "stop",
            }
        }
    }
    wnmbench_scenario_config = {
        "scenario": "wnmbench",
        "configuration": {
            "setup": {
                "centreid_min": WNMBENCH_CENTRE_ID_MIN,
                "centreid_max": WNMBENCH_CENTRE_ID_MAX,
                "number": perf_set['msg_count'],
                "delay": perf_set['msg_delay']
            }
        }
    }
#    print(f"Scenario message: {json.dumps(mqttx_scenario_start, indent=4)}")
    pub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    assert pub_client.connected_flag
    pub_client.publish("config/a/wis2", json.dumps(mqttx_scenario_start))
    time.sleep((perf_set['mqttx_concurrent']*0.2)+5)  # Wait for publish
#    print(f"Scenario message: {json.dumps(wnmbench_scenario_config, indent=4)}")
    sub_client.publish("config/a/wis2", json.dumps(wnmbench_scenario_config))
    time.sleep(message_pace)  # Wait for publish

    result_msgs = wait_for_results(sub_client, perf_set['mqttx_tmout'] + 10, perf_set['mqttx_tmout'])
    assert len(result_msgs) == len(sub_result_topics)
    for mesg_count in result_msgs:
        print(f"MQTTx Client: {mesg_count['topic'].split('/')[3]}    Total Received: {mesg_count['max_recv']}    Expected: {200 * perf_set['msg_count'] * perf_set['mqttx_concurrent']}")
    sub_client.loop_stop()
    sub_client.disconnect()
    del sub_client
    time.sleep(test_pace)


@pytest.mark.parametrize("perf_set", extreme_perf_settings)
def test_4_mqtt_broker_extremeperf(perf_set):
    print("\n4. WIS2 Broker HIGH Performance Test")
    print(f"MQTTx Concurrent: {perf_set['mqttx_concurrent']}  MQTTx Timeout: {perf_set['mqttx_tmout']}  Message Count: {perf_set['msg_count']}  Message Delay: {perf_set['msg_delay']}")
    sub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    sub_client.subscribe("result/a/wis2/#", qos=1)
    time.sleep(message_pace)  # Wait for subscription
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    broker_info = urlparse(mqtt_broker_test)
    mqttx_scenario_start = {
        "scenario": "mqttx",
        "configuration": {
            "setup": {
                "centreid_min": MQTTX_CENTRE_ID_MIN,
                "centreid_max": MQTTX_CENTRE_ID_MAX,
                "timeout": perf_set['mqttx_tmout'],
                "concurrent": perf_set['mqttx_concurrent'],
                "username": broker_info.username,
                "password": broker_info.password,
                "broker": f"{broker_info.scheme}://{broker_info.hostname}",
                "port": broker_info.port,
                "action": "start",
                "topic": "origin/a/wis2/#"
            }
        }
    }
    mqttx_scenario_stop = {
        "scenario": "mqttx",
        "configuration": {
            "setup": {
                "centreid_min": MQTTX_CENTRE_ID_MIN,
                "centreid_max": MQTTX_CENTRE_ID_MAX,
                "action": "stop",
            }
        }
    }
    wnmbench_scenario_config = {
        "scenario": "wnmbench",
        "configuration": {
            "setup": {
                "centreid_min": WNMBENCH_CENTRE_ID_MIN,
                "centreid_max": WNMBENCH_CENTRE_ID_MAX,
                "number": perf_set['msg_count'],
                "delay": perf_set['msg_delay']
            }
        }
    }
#    print(f"Scenario message: {json.dumps(mqttx_scenario_start, indent=4)}")
    pub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    assert pub_client.connected_flag
    pub_client.publish("config/a/wis2", json.dumps(mqttx_scenario_start))
    time.sleep((perf_set['mqttx_concurrent']*0.2)+5)  # Wait for publish
#    print(f"Scenario message: {json.dumps(wnmbench_scenario_config, indent=4)}")
    sub_client.publish("config/a/wis2", json.dumps(wnmbench_scenario_config))
    time.sleep(message_pace)  # Wait for publish

    result_msgs = wait_for_results(sub_client, perf_set['mqttx_tmout'] + 10, perf_set['mqttx_tmout'])
    assert len(result_msgs) == len(sub_result_topics)
    for mesg_count in result_msgs:
        print(f"MQTTx Client: {mesg_count['topic'].split('/')[3]}    Total Received: {mesg_count['max_recv']}    Expected: {200 * perf_set['msg_count'] * perf_set['mqttx_concurrent']}")
    sub_client.loop_stop()
    sub_client.disconnect()
    del sub_client
    time.sleep(test_pace)


@pytest.mark.parametrize("perf_set", heroic_perf_settings)
def test_5_mqtt_broker_heroicperf(perf_set):
    print("\n5. WIS2 Broker Heroique Performance Test")
    print(f"MQTTx Concurrent: {perf_set['mqttx_concurrent']}  MQTTx Timeout: {perf_set['mqttx_tmout']}  Message Count: {perf_set['msg_count']}  Message Delay: {perf_set['msg_delay']}")
    sub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    sub_client.subscribe("result/a/wis2/#", qos=1)
    time.sleep(message_pace)  # Wait for subscription
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    broker_info = urlparse(mqtt_broker_test)
    mqttx_scenario_start = {
        "scenario": "mqttx",
        "configuration": {
            "setup": {
                "centreid_min": MQTTX_CENTRE_ID_MIN,
                "centreid_max": MQTTX_CENTRE_ID_MAX,
                "timeout": perf_set['mqttx_tmout'],
                "concurrent": perf_set['mqttx_concurrent'],
                "username": broker_info.username,
                "password": broker_info.password,
                "broker": f"{broker_info.scheme}://{broker_info.hostname}",
                "port": broker_info.port,
                "action": "start",
                "topic": "origin/a/wis2/#"
            }
        }
    }
    mqttx_scenario_stop = {
        "scenario": "mqttx",
        "configuration": {
            "setup": {
                "centreid_min": MQTTX_CENTRE_ID_MIN,
                "centreid_max": MQTTX_CENTRE_ID_MAX,
                "action": "stop",
            }
        }
    }
    wnmbench_scenario_config = {
        "scenario": "wnmbench",
        "configuration": {
            "setup": {
                "centreid_min": WNMBENCH_CENTRE_ID_MIN,
                "centreid_max": WNMBENCH_CENTRE_ID_MAX,
                "number": perf_set['msg_count'],
                "delay": perf_set['msg_delay']
            }
        }
    }
#    print(f"Scenario message: {json.dumps(mqttx_scenario_start, indent=4)}")
    pub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    assert pub_client.connected_flag
    pub_client.publish("config/a/wis2", json.dumps(mqttx_scenario_start))
    time.sleep((perf_set['mqttx_concurrent']*0.2)+5)  # Wait for publish
#    print(f"Scenario message: {json.dumps(wnmbench_scenario_config, indent=4)}")
    sub_client.publish("config/a/wis2", json.dumps(wnmbench_scenario_config))
    time.sleep(message_pace)  # Wait for publish

    result_msgs = wait_for_results(sub_client, perf_set['mqttx_tmout'] + 60, perf_set['mqttx_tmout'])
    assert len(result_msgs) == len(sub_result_topics)
    for mesg_count in result_msgs:
        print(f"MQTTx Client: {mesg_count['topic'].split('/')[3]}    Total Received: {mesg_count['max_recv']}    Expected: {200 * perf_set['msg_count'] * perf_set['mqttx_concurrent']}")
    sub_client.loop_stop()
    sub_client.disconnect()
    del sub_client
    time.sleep(test_pace)

