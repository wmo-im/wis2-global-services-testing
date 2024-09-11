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
from dotenv import load_dotenv
load_dotenv()

# Connection strings for the development global broker and message generator
# Access the environment variables
scenario_broker_url = os.getenv('SCENARIO_BROKER')
global_broker_url = os.getenv('GLOBAL_BROKER')
noaa_broker_plain = os.getenv('NOAA_BROKER_PLAIN')
noaa_broker_tls = os.getenv('NOAA_BROKER_TLS')
noaa_broker_ws = os.getenv('NOAA_BROKER_WS')

# Topics
sub_global_topics = [
    "origin/a/wis2/#",
    "cache/a/wis2/#"
]

sub_node_topics = [
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
    "origin/a/wis2/io-wis2dev-16-test/metadata",
    "origin/a/wis2/io-wis2dev-16-test/metadata/weather/surface-based-observations/synop",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/aviation/metar",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/surface-based-observations/synop",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/surface-based-observations/ship-hourly",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/space-based-observations/alos-2",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/space-based-observations/amazonia-1",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/prediction/analysis/nowcasting/deterministic/global",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/prediction/analysis/seasonal/deterministic/global",
    "origin/a/wis2/io-wis2dev-16-test/data/core/climate/surface-based-observations/monthly",
    "origin/a/wis2/io-wis2dev-16-test/data/core/climate/surface-based-observations/daily",
    "origin/a/wis2/io-wis2dev-16-test/data/core/cryosphere/experimental",
    "origin/a/wis2/io-wis2dev-16-test/data/core/cryosphere/experimental/graviton/lambda",
    "origin/a/wis2/io-wis2dev-16-test/data/core/hydrology/experimental",
    "origin/a/wis2/io-wis2dev-16-test/data/core/hydrology/experimental/turbulent/laminar/flows",
    "origin/a/wis2/io-wis2dev-16-test/data/core/atmospheric-composition/experimental",
    "origin/a/wis2/io-wis2dev-16-test/data/core/atmospheric-composition/experimental/smog/tests",
    "origin/a/wis2/io-wis2dev-16-test/data/core/ocean/surface-based-observations/moored-bouys",
    "origin/a/wis2/io-wis2dev-16-test/data/core/ocean/surface-based-observations/sea-ice"
]

pub_invalid_topics = [
    "origin/a/wis2/io-wis2dev-16-test/data",
    "origin/a/wis2/io-wis2dev-16-test/data/core",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/surface-based-observations",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/surface-sed-observations/synop",
    "origin/a/wis2/io-wis2dev-16-test/metadata/weather/surface-observation",
    "origin/a/wis2/io-wis2dev-16-test/metadata/weather/surface-based-observation/synop/test",
    "origin/a/wis2/io-wis2dev-16-test/database/core/weather/surface-based-observation/synop",
    "origin/a/wis2/io-wis2dev-16-test/data/corefile/weather/surface-based-observation/synop",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/surface-based-observation/synop/prediction",
    "origin/a/wis2/io-wis2dev-16-test/data/recommended/weather/surface-based-observation/synop",
    "origin/a/wis2/io-wis2dev-16-test/data/core/geospatial/surface-based-observation/synop",
    "origin/a/wis2/io-wis2dev-16-test/data/core/ibweather/surface-based-observation/dynop",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/sputnic-satellite",
    "origin/a/wis2/io-wis2dev-16-test/data/core/atmospheric-composition/satellite",
    "origin/a/wis2/io-wis2dev-16-test/data/core/atmospheric-composition",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/prediction",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/prediction/analysis",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/prediction/analysis/nowcasting",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/prediction/analysis/short-range",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/prediction/hindcast",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/prediction/hindcast/short-range",
    "origin/a/wis2/io-wis2dev-16-test/data/core/weather/prediction/hindcast/nowcasting"
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

center_id_regex = re.compile(r"io-wis2dev-([0-9]{2})-test")

def flag_on_connect(client, userdata, flags, rc, properties=None):
    print(rc)
    client.connected_flag = True

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


def setup_mqtt_client(connection_info: str):
    rand_id = "NOAA-mqttx-" + str(uuid.uuid4())[:10]
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
        tls_settings['cert_reqs'] = ssl.CERT_NONE
        client.tls_set(**tls_settings)
    client.connect(host=connection_info.hostname, port=connection_info.port, properties=properties)
    client.loop_start()
    time.sleep(1.5)  # Wait for connection
    if not client.is_connected():
        raise Exception("Failed to connect to MQTT broker")
    return client

def gen_wnm_mesg(topic, filename):
    wis2_notification_message = {
      "id": str(uuid.uuid4()),
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


@pytest.mark.parametrize("mqtt_broker_url", [noaa_broker_plain])
def test_1_mqtt_broker_connectivity(mqtt_broker_url):
    print("\n1. GB MQTT Broker Connectivity" + mqtt_broker_url)
    client = setup_mqtt_client(mqtt_broker_url)
    assert client.connected_flag
    client.disconnect()
    time.sleep(0.5)
#    del client


@pytest.mark.parametrize("mqtt_broker_url", [noaa_broker_tls])
def test_2_mqtt_broker_tls_connectivity(mqtt_broker_url):
    print("\n1. GB MQTT SSL/TLS Broker Connectivity" + mqtt_broker_url)
    client = setup_mqtt_client(mqtt_broker_url)
    assert client.connected_flag
    client.disconnect()
    time.sleep(0.5)
#    del client


@pytest.mark.parametrize("topic", sub_global_topics)
def test_3_mqtt_broker_subscription_read(topic):
    print("\n2. GB MQTT Broker Subscription")
    print(f"Subscribing to topic: {topic}")
    client = setup_mqtt_client(noaa_broker_plain)
    client.loop_start()
    result, mid = client.subscribe(topic)
    time.sleep(1)  # Wait for subscription
    assert result is mqtt.MQTT_ERR_SUCCESS
    assert client.connected_flag
    assert client.subscribed_flag
    assert client.message_flag
    client.loop_stop()
    client.disconnect()
    time.sleep(2)  # Wait for subscription
#    del client

@pytest.mark.parametrize("topic", pub_valid_topics)
def test_4_mqtt_broker_publication_write(topic):
    print("\n2. GB MQTT Broker Publication Submit")
    print(f"Publishing to topic: {topic}")
    sub_topic = "/".join(topic.split('/')[0:4]) + "/#"
    client = setup_mqtt_client(global_broker_url)
    client.loop_start()
    result, mid = client.subscribe(sub_topic)
    time.sleep(0.5)  # Wait for subscription
    result, mid = client.publish(topic, json.dumps(gen_wnm_mesg(topic,"t1t2A1A2iiCCCC_yymmddHHMMSS.bufr")))
    time.sleep(0.5)  # Wait for subscription
    assert result is mqtt.MQTT_ERR_SUCCESS
    assert client.connected_flag
    assert client.subscribed_flag
    assert client.message_flag
    client.loop_stop()
    client.disconnect()
    time.sleep(1)  # Wait for subscription
#    del client

def test_5_mqtt_broker_antiloop():
    print("\n3. WIS2 Broker Antiloop Test")
    wnm_scenario_config = {
        "scenario": "wnmtest",
        "configuration": {
            "setup": {
                "centreid_min": 12,
                "centreid_max": 14,
                "number": 4
            },
            "wnm": {
                "id": str(uuid.uuid4())
            }
        }
    }
    sub_client = setup_mqtt_client(noaa_broker_tls)
    sub_client.loop_start()
    sub_client.subscribe("origin/a/wis2/io-wis2dev-12-test/#")
    sub_client.subscribe("origin/a/wis2/io-wis2dev-13-test/#")
    sub_client.subscribe("origin/a/wis2/io-wis2dev-14-test/#")
    time.sleep(1)  # Wait for subscription
    pub_client = setup_mqtt_client(scenario_broker_url)
    pub_client.loop_start()
    pub_client.publish("config/a/wis2", json.dumps(wnm_scenario_config))
    time.sleep(2)  # Wait for messages
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    assert sub_client.message_flag
    assert len(sub_client._userdata['received_messages']) == 1
    sub_client.loop_stop()
    sub_client.disconnect()
    pub_client.loop_stop()
    pub_client.disconnect()
    time.sleep(1)

def test_6_node_invalid_centre_id_test():
    print("\n4. WIS2 Node Invalid Centre ID Test")

    wnm_scenario_config_12 = {
        "scenario": "wnmtest",
        "configuration": {
            "setup": {
                "centreid": 12,
                "number": 1
            },
            "wnm": {
                "properties": {
                "data_id": pub_valid_topics[0] 
                }
            }
        }
    }
    
    wnm_scenario_config_13 = {
        "scenario": "wnmtest",
        "configuration": {
            "setup": {
                "centreid": 13,
                "number": 1
            },
            "wnm": {
                "properties": {
                "data_id": pub_valid_topics[1] 
                }
            }            
        }
    }

    wnm_scenario_config_14 = {
        "scenario": "wnmtest",
        "configuration": {
            "setup": {
                "centreid": 14,
                "number": 1
            },
            "wnm": {
                "properties": {
                "data_id": pub_valid_topics[2] 
                }
            }            
        }
    }

    sub_client = setup_mqtt_client(noaa_broker_tls)
    sub_client.loop_start()
    sub_client.subscribe("origin/a/wis2/io-wis2dev-12-test/#")
    sub_client.subscribe("origin/a/wis2/io-wis2dev-13-test/#")
    sub_client.subscribe("origin/a/wis2/io-wis2dev-14-test/#")
    time.sleep(1)  # Wait for subscription
    pub_client = setup_mqtt_client(scenario_broker_url)
    pub_client.loop_start()
    pub_client.publish("config/a/wis2", json.dumps(wnm_scenario_config_14))
    pub_client.publish("config/a/wis2", json.dumps(wnm_scenario_config_12))
    pub_client.publish("config/a/wis2", json.dumps(wnm_scenario_config_13))
    time.sleep(3)  # Wait for messages
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    assert sub_client.message_flag
    assert len(sub_client._userdata['received_messages']) == 0
    sub_client.loop_stop()
    sub_client.disconnect()
    pub_client.loop_stop()
    pub_client.disconnect()
    time.sleep(1)

@pytest.mark.parametrize("topic", pub_valid_topics)
def test_7_valid_topic_test(topic):
    print("\n4. WIS2 GB Valid Message Test")
    cent_id_num = center_id_regex.search(topic).group(1)
    sub_client = setup_mqtt_client(noaa_broker_tls)
    sub_client.loop_start()
    sub_client.subscribe(f"origin/a/wis2/io-wis2dev-{cent_id_num}-test/#")
    wnm_scenario_config = {
       "scenario": "wnmtest",
       "configuration": {
          "setup": {
             "centreid": cent_id_num,
             "number": 1
          }
       }
    }
    pub_client = setup_mqtt_client(global_broker_url)
    pub_client.publish(topic, json.dumps(gen_wnm_mesg(topic,"t1t2A1A2iiCCCC_yymmddHHMMSS.bufr")))
    time.sleep(2)  # Wait for messages
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    assert len(sub_client._userdata['received_messages']) == 1
    sub_client.loop_stop()
    sub_client.disconnect()
    pub_client.loop_stop()
    pub_client.disconnect()
    time.sleep(1)
    

@pytest.mark.parametrize("topic", pub_valid_topics)
def test_8_valid_msg_test(topic):
    print("\n4. WIS2 GB Valid Message Test")
    match = center_id_regex.search(topic)
    cent_id_num = center_id_regex.search(topic).group(1)
    sub_client = setup_mqtt_client(noaa_broker_tls)
    sub_client.loop_start()
    sub_client.subscribe(f"origin/a/wis2/io-wis2dev-{cent_id_num}-test/#")
    wnm_scenario_config = {
       "scenario": "wnmtest",
       "configuration": {
          "setup": {
             "centreid": cent_id_num,
             "number": 1
          }
       }
    }
    pub_client = setup_mqtt_client(scenario_broker_url)
    pub_client.publish(f"config/a/wis2", json.dumps(wnm_scenario_config))
    time.sleep(2)  # Wait for messages
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    assert sub_client.message_flag
    assert len(sub_client._userdata['received_messages']) == 1
    sub_client.loop_stop()
    sub_client.disconnect()
    pub_client.loop_stop()
    pub_client.disconnect()
    time.sleep(1)
    
@pytest.mark.parametrize("topic", pub_invalid_topics)
def test_8_invalid_topic_test(topic):
    print("\n4. WIS2 GB Invalid Topic Test")
    cent_id_num = center_id_regex.search(topic).group(1)
    sub_client = setup_mqtt_client(noaa_broker_tls)
    sub_client.loop_start()
    sub_client.subscribe(f"origin/a/wis2/io-wis2dev-{cent_id_num}-test/#")
    wnm_scenario_config = {
       "scenario": "wnmtest",
       "configuration": {
          "setup": {
             "centreid": cent_id_num,
             "number": 1
          }
       }
    }
    print("\n4. " + json.dumps(wnm_scenario_config))
    pub_client = setup_mqtt_client(global_broker_url)
    pub_client.publish(topic, json.dumps(gen_wnm_mesg(topic,"t1t2A1A2iiCCCC_yymmddHHMMSS.bufr")))
    time.sleep(2)  # Wait for messages
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    assert len(sub_client._userdata['received_messages']) == 0
    sub_client.loop_stop()
    sub_client.disconnect()
    pub_client.loop_stop()
    pub_client.disconnect()
    time.sleep(1)
    
@pytest.mark.parametrize("mesg", pub_invalid_msg)
def test_9_invalid_msg_test(mesg):
    print("\n4. WIS2 GB Invalid Message Test")
    sub_client = setup_mqtt_client(noaa_broker_tls)
    sub_client.loop_start()
    sub_client.subscribe(f"origin/a/wis2/io-wis2dev-18-test/#")
    wnm_scenario_config = {
       "scenario": "wnmtest",
       "configuration": {
          "setup": {
             "centreid": 18,
             "number": 1
          },
          "wnm": mesg
       }
    }
    print("\n4. " + json.dumps(wnm_scenario_config))
    pub_client = setup_mqtt_client(scenario_broker_url)
    pub_client.publish(f"config/a/wis2", json.dumps(wnm_scenario_config))
    time.sleep(2)  # Wait for messages
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    assert len(sub_client._userdata['received_messages']) == 0
    sub_client.loop_stop()
    sub_client.disconnect()
    pub_client.loop_stop()
    pub_client.disconnect()
    time.sleep(1)
