import json
import uuid
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
from pywis_pubsub.validation import validate_message
from pywis_pubsub.verification import verify_data
from pywis_pubsub.publish import create_message
from pywis_pubsub.schema import sync_schema as pw_sync
from pywis_pubsub.mqtt import MQTTPubSubClient
from dotenv import load_dotenv
load_dotenv()
# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared_utils import mqtt_helpers


# Connection strings for the development global broker and message generator
# Access the environment variables
scenario_broker_url = os.getenv('SCENARIO_BROKER')
noaa_broker_url = os.getenv('NOAA_BROKER')
noaa_broker_plain = os.getenv('NOAA_BROKER_PLAIN')
noaa_broker_tls = os.getenv('NOAA_BROKER_TLS')
noaa_broker_ws = os.getenv('NOAA_BROKER_WS')

# Topics
sub_global_topics = [
    "origin/a/wis2/#",
    "cache/a/wis2/#"
]

sub_node_topics = [
    "origin/a/wis2/io_wis2dev-11-test/#",
    "origin/a/wis2/io_wis2dev-12-test/#",
    "origin/a/wis2/io_wis2dev-13-test/#",
    "origin/a/wis2/io_wis2dev-14-test/#",
    "origin/a/wis2/io_wis2dev-15-test/#",
    "origin/a/wis2/io_wis2dev-16-test/#",
    "origin/a/wis2/io_wis2dev-17-test/#",
    "origin/a/wis2/io_wis2dev-18-test/#",
    "origin/a/wis2/io_wis2dev-19-test/#",
    "origin/a/wis2/io_wis2dev-20-test/#"
]

pub_valid_topics = [
    "origin/a/wis2/io-wis2dev-11-test/data/core/weather/surface-based-observation/synop",
    "origin/a/wis2/io-wis2dev-12-test/data/core/weather/surface-based-observation/synop",
    "origin/a/wis2/io-wis2dev-13-test/data/core/weather/prediction/analysis/nowcasting/deterministic/global",
    "origin/a/wis2/io-wis2dev-14-test/data/core/climate/surface-based-observation/daily",
    "origin/a/wis2/io-wis2dev-15-test/data/core/cryosphere/experimental",
    "origin/a/wis2/io-wis2dev-16-test/data/core/hydrology/experimental",
    "origin/a/wis2/io-wis2dev-17-test/data/core/ocean/surface-based-observation/moored-bouys",
    "origin/a/wis2/io-wis2dev-18-test/data/core/ocean/surface-based-observation/sea-ice",
    "origin/a/wis2/io-wis2dev-19-test/data/core/weather/aviation/metar",
    "origin/a/wis2/io-wis2dev-20-test/data/core/weather/aviation/taf"
]

pub_invalid_topics = [
    "backup/a/wis2/io-wis2dev-11-test/data/core/weather/surface-based-observation/synop",
    "origin/b/wis2/io-wis2dev-12-test/data/core/weather/surface-based-observation/synop",
    "origin/a/wis3/io-wis2dev-13-test/data/core/weather/surface-based-observation/synop",
    "origin/a/wis2/io-wis2dev-14-test/metadata/weather/surface-based-observation/synop",
    "origin/a/wis2/io-wis2dev-15-test/data/recommended/weather/surface-based-observation/synop",
    "origin/a/wis2/io-wis2dev-16-test/data/core/geospatial/surface-based-observation/synop",
    "origin/a/wis2/io-wis2dev-17-test/data/core/weather/surface-sed-observation/synop",
    "origin/a/wis2/io-wis2dev-18-test/data/core/weather/surface-based-observation/dynop",
    "origin/a/wis2/io-wis2dev-19-test/data/core/weather/surface-based-observation/synop/prediction",
    "origin/a/wis2/io-wis2dev-20-test/data/core/weather/satellite"
]

pub_invalid_msg = [
    {"id": False },
    {"id": "This is NOT a UUID" },
    {"type": False },
    {"type": "Not Feature" },
    {"links": [{"href": False }]},
    {"links": [{"rel": False }]},
    {"conformsTo": [False] },
    {"conformsTo": ["This is NOT correct"] },
    {"properties": {"data_id": False }},
    {"properties": {"datetime": False }},
    {"properties": {"datetime": "Not RFC3339 Compliant" }},
    {"properties": {"datetime": False, "end_datetime": "2024-07-20t19:12:29z" }},
    {"properties": {"datetime": False, "start_datetime": "2024-07-20t19:12:29z" }},
    {"properties": {"pubtime": False }},
    {"properties": {"pubtime": "2024-07-21t18:58:34z" }},
    {"properties": {"start_datetime": "2024-07-20t19:12:29z", "end_datetime": "2024-07-20t19:12:29z" }}
]

center_id_regex = re.compile("io_wis2dev-([0-9])-test")

def flag_on_connect(client, userdata, flags, rc, properties=None):
    # print("Connected with result code " + str(rc))
    if rc == 0:
        client.connected_flag = True
    else:
        client.connected_flag = False


def flag_on_subscribe(client, userdata, mid, granted_qos, properties=None):
    print("Subscribed with mid " + str(mid) + " and QoS " + str(granted_qos[0]))
    client.subscribed_flag = True


def flag_on_message(client, userdata, msg):
    print(f"Received message on topic {msg.topic} with payload {msg.payload}")
    msg_json = json.loads(msg.payload.decode())
    # add topic
    msg_json['topic'] = msg.topic
    client._userdata['received_messages'].append(msg_json)
    client.message_flag = True


def setup_mqtt_client(connection_info: str, verify_certs: bool):
    rand_id = "wis2_testing" + str(uuid.uuid4())[:10]
    client = mqtt.Client(client_id=rand_id, protocol=mqtt.MQTTv5, userdata={'received_messages': []})
    client.on_connect = flag_on_connect
    client.on_subscribe = flag_on_subscribe
    client.on_message = flag_on_message
    connection_info = urlparse(connection_info)
    client.username_pw_set(connection_info.username, connection_info.password)
    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = 300  # seconds
    if connection_info.port in [443, 8883]:
        tls_settings = { 'tls_version': 2 }
        if not verify_certs:
            tls_settings['cert_reqs'] = ssl.CERT_NONE
        client.tls_set(**tls_settings)
    else:
        client.tls_set()
    client.connect(host=connection_info.hostname, port=connection_info.port, properties=properties)
    client.loop_start()
    time.sleep(2)  # Wait for connection
#    if not client.is_connected():
#        raise Exception("Failed to connect to MQTT broker")
    return client

def gen_wnm_mesg(topic, filename):
    wis2_notification_message = {
      "id": uuid.uuid4(),
      "type": "Feature",
      "version": "v04",
      "geometry": {
        "type": "Point",
        "coordinates": [ -84.8428, 39.7572 ]
      },
      "properties": {
        "data_id": topic + "/" + filename,
        "datetime": "2024-08-28T19:35:00Z",
        "pubtime": "2024-08-28T19:25:07Z",
        "wigos_station_identifier": "0-840-0-KRID"
      },
      "links": [
        {
          "rel": "via",
          "type": "text/html",
          "href": "https://oscar.wmo.int/surface/#/search/station/stationReportDetails/0-840-0-KRID"
        }
      ]
    }
    return(wis2_notification_message)


@pytest.mark.parameterize("mqtt_broker_url", [noaa_broker_plain, noaa_broker_tls, noaa_broker_ws])
def test_1_mqtt_broker_connectivity(mqtt_broker_url):
    print("\n1. GB MQTT Broker Connectivity" + mqtt_broker_url)
    client = setup_mqtt_client(noaa_broker_url, False)
    assert client.on_connect is True
    client.conn.disconnect()
    del client


@pytest.mark.parameterize("mqtt_broker_url", [noaa_broker_tls, noaa_broker_ws])
def test_2_mqtt_broker_tls_connectivity(mqtt_broker_url):
    print("\n1. GB MQTT SSL/TLS Broker Connectivity" + mqtt_broker_url)
    client = setup_mqtt_client(noaa_broker_url, True)
    assert client.on_connect is True
    client.conn.disconnect()
    del client


@pytest.mark.parametrize("topic", sub_global_topics)
def test_3_mqtt_broker_subscription_read(topic):
    print("\n2. GB MQTT Broker Subscription")
    print(f"Subscribing to topic: {topic}")
    client = setup_mqtt_client(noaa_broker_url, True)
    client.conn.subscribed_flag = False
    client.conn.message_flag = False
    client.conn.on_subscribe = flag_on_subscribe
    client.conn.on_connect = flag_on_connect
    client.conn.loop_start()
    result, mid = client.conn.subscribe(topic)
    time.sleep(5)  # Wait for subscription
    assert result is mqtt.MQTT_ERR_SUCCESS
    assert client.conn.subscribed_flag is True
    assert client.conn.message_flag is True
    client.conn.loop_stop()
    client.conn.disconnect()
    del client

@pytest.mark.parametrize("topic", pub_valid_topics)
def test_4_mqtt_broker_publication_write(topic):
    print("\n2. GB MQTT Broker Publication Submit")
    print(f"Publishing to topic: {topic}")
    client = setup_mqtt_client(noaa_broker_url, True)
    time.sleep(5)  # Wait for subscription
    client.pub(topic=topic, message=json.dumps(gen_wnm_mesg()))
    assert client.conn.subscribed_flag is False
    assert client.conn.message_flag is False
    client.conn.loop_stop()
    client.conn.disconnect()
    del client

def test_5_mqtt_broker_antiloop():
    print("\n3. WIS2 Broker Antiloop Test")

    sub_client = setup_mqtt_client(noaa_broker_url, True)
    sub_client.conn.subscribed_flag = False
    sub_client.conn.message_flag = False
    sub_client.conn.on_subscribe = flag_on_subscribe
    sub_client.conn.on_connect = flag_on_connect
    sub_client.subscribe("origin/a/wis2/io-wis2dev-11-test/#", qos=1)
    sub_client.subscribe("origin/a/wis2/io-wis2dev-12-test/#", qos=1)
    print(f"Subscribed to topics: origin/a/wis2/io-wis2dev-11-test/# origin/a/wis2/io-wis2dev-12-test/#")

    test_uuid = uuid.uuid4()
    wnm_scenario_config_11 = {
        "scenario": "wnmgen",
        "configuration": {
            "setup": {
                "centreid": 11,
                "number": 10
            },
            "wnm": {
                "properties": {
                    "data_id": test_uuid,
                }
            }
        }
    }
    wnm_scenario_config_12 = {
        "scenario": "wnmgen",
        "configuration": {
            "setup": {
                "centreid": 12,
                "number": 10
            },
            "wnm": {
                "properties": {
                    "data_id": test_uuid,
                }
            }
        }
    }
    print(wnm_scenario_config_11)
    print(wnm_scenario_config_12)
    pub_client = setup_mqtt_client(scenario_broker_url, True)
    pub_client.pub(topic=pub_valid_topics[1], message=json.dumps(wnm_scenario_config_11))
    pub_client.pub(topic=pub_valid_topics[0], message=json.dumps(wnm_scenario_config_12))
    time.sleep(10)  # Wait for messages
    client_msgs = [m for m in sub_client._userdata['received_messages']]
    sub_client.loop_stop()
    sub_client.disconnect()
    assert len(client_msgs) > 1

def test_6_node_invalid_centre_id_test():
    print("\n4. WIS2 Node Invalid Centre ID Test")

    sub_client = setup_mqtt_client(noaa_broker_url, True)
    for sub_topic in sub_node_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")

    wnm_scenario_config_11 = {
       "scenario": "wnmgen",
       "configuration": {
          "setup": {
             "centreid": 11,
             "number": 1
          }
       }
    }
    
    wnm_scenario_config_12 = {
       "scenario": "wnmgen",
       "configuration": {
          "setup": {
             "centreid": 12,
             "number": 1
          }
       }
    }

    pub_client = setup_mqtt_client(scenario_broker_url, True)
    pub_client.pub(topic=pub_valid_topics[0], message=json.dumps(wnm_scenario_config_12))
    pub_client.pub(topic=pub_valid_topics[1], message=json.dumps(wnm_scenario_config_11))
    time.sleep(10)  # Wait for messages
    sub_client_msgs = [m for m in sub_client._userdata['received_messages']]
    sub_client.loop_stop()
    sub_client.disconnect()
    assert len(sub_client_msgs) > 0

@pytest.mark.parametrize("topic", pub_valid_topics)
def test_7_valid_msg_test(topic):
    print("\n4. WIS2 GB Valid Message Test")
    sub_client = setup_mqtt_client(noaa_broker_url, True)
    for sub_topic in sub_node_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    cent_id_num = center_id_regex.search(topic).group(1)
    wnm_scenario_config = {
       "scenario": "wnmgen",
       "configuration": {
          "setup": {
             "centreid": cent_id_num,
             "number": 5
          }
       }
    }
    pub_client = setup_mqtt_client(scenario_broker_url, True)
    pub_client.pub(topic=topic, message=json.dumps(wnm_scenario_config))
    time.sleep(5)  # Wait for messages
    sub_client_msgs = [m for m in sub_client._userdata['received_messages']]
    sub_client.loop_stop()
    sub_client.disconnect()
    assert len(sub_client_msgs) < 5

@pytest.mark.parametrize("topic", pub_invalid_topics)
def test_8_node_invalid_topic_test(topic):
    print("\n5. GB Node Invalid Topic Test")
    cent_id_num = center_id_regex.search(topic).group(1)
    sub_client = setup_mqtt_client(noaa_broker_url, True)
    for sub_topic in sub_node_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    wnm_scenario_config = {
        "scenario": "wnmgen",
        "configuration": {
            "setup": {
                "centreid": cent_id_num,
                "number": 1,
            }
        }
    }
    pub_client = setup_mqtt_client(scenario_broker_url, True)
    pub_client.pub(topic=topic, message=json.dumps(wnm_scenario_config))
    time.sleep(5)  # Wait for messages
    sub_client_msgs = [m for m in sub_client._userdata['received_messages']]
    sub_client.loop_stop()
    sub_client.disconnect()
    assert len(sub_client_msgs) > 1

@pytest.mark.parametrize("mesg", pub_invalid_msg)
def test_9_node_invalid_message_test(mesg):
    print("\n5. GB Node Invalid Message Test")
    sub_client = setup_mqtt_client(noaa_broker_url, True)
    for sub_topic in sub_node_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    wnm_scenario_config = {
        "scenario": "wnmtest",
        "configuration": {
            "setup": {
                "centreid": 11,
                "number": 1
            },
            "wnm": json.dumps(mesg)
        }
    }
    pub_client = setup_mqtt_client(scenario_broker_url, True)
    pub_client.pub(topic="?topic?", message=json.dumps(wnm_scenario_config))
    time.sleep(5)  # Wait for messages
    sub_client_msgs = [m for m in sub_client._userdata['received_messages']]
    sub_client.loop_stop()
    sub_client.disconnect()
    assert len(sub_client_msgs) > 1

