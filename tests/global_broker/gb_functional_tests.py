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
sub_node_topics = [
    "origin/a/wis2/io_wis2dev-12-test/#",
    "origin/a/wis2/io_wis2dev-13-test/#",
    "origin/a/wis2/io_wis2dev-14-test/#",
    "origin/a/wis2/io_wis2dev-15-test/#",
]

# Write Test Valid Topics
pub_write_topics = [
    "origin/a/wis2/io-wis2dev-12-test/metadata",
    "cache/a/wis2/io-wis2dev-12-test/metadata/core/weather/surface-based-observations/synop",
    "origin/a/wis2/io-wis2dev-13-test/data/core/weather/aviation/metar",
    "cache/a/wis2/io-wis2dev-13-test/data/core/weather/surface-based-observations/synop"
]

pub_general_topics = [
    "origin/a/wis2/io-wis2dev-12/#",
    "cache/a/wis2/io-wis2dev-12-test/metadata/#",
    "origin/a/wis2/io-wis2dev-13-test/data/#",
    "cache/a/wis2/io-wis2dev-13-test/data/#"
]

# Valid Test Topics
pub_valid_topics = [
    "origin/a/wis2/io-wis2dev-12-test/metadata",
    "origin/a/wis2/io-wis2dev-12-test/metadata/core/weather/surface-based-observations/synop",
    "origin/a/wis2/io-wis2dev-13-test/data/core/weather/aviation/metar",
    "origin/a/wis2/io-wis2dev-13-test/data/core/weather/surface-based-observations/synop",
    "origin/a/wis2/io-wis2dev-14-test/data/core/weather/surface-based-observations/ship",
    "origin/a/wis2/io-wis2dev-14-test/data/core/weather/space-based-observations/sentinel-2b/msi",
    "origin/a/wis2/io-wis2dev-15-test/data/core/weather/space-based-observations/swot/poseidon-3c",
    "origin/a/wis2/io-wis2dev-15-test/data/core/space-weather/space-based-observations/xmm-newton/epic",
    "origin/a/wis2/io-wis2dev-11-test/data/core/space-weather/space-based-observations/themis-a/scm",
    "origin/a/wis2/io-wis2dev-11-test/data/core/weather/prediction/analysis/nowcasting/deterministic/global",
    "origin/a/wis2/io-wis2dev-12-test/data/core/weather/prediction/analysis/seasonal/deterministic/global",
    "origin/a/wis2/io-wis2dev-12-test/data/core/climate/surface-based-observations/monthly",
    "origin/a/wis2/io-wis2dev-13-test/data/core/climate/surface-based-observations/daily",
    "origin/a/wis2/io-wis2dev-13-test/data/core/cryosphere/experimental",
    "origin/a/wis2/io-wis2dev-14-test/data/core/cryosphere/experimental/graviton/lambda",
    "origin/a/wis2/io-wis2dev-14-test/data/core/hydrology/experimental",
    "origin/a/wis2/io-wis2dev-15-test/data/core/hydrology/experimental/turbulent/laminar/flows",
    "origin/a/wis2/io-wis2dev-15-test/data/core/atmospheric-composition/experimental",
    "origin/a/wis2/io-wis2dev-13-test/data/core/atmospheric-composition/experimental/smog/tests",
    "origin/a/wis2/io-wis2dev-15-test/data/core/ocean/surface-based-observations/drifting-buoys",
    "origin/a/wis2/io-wis2dev-14-test/data/core/ocean/surface-based-observations/sea-ice"
]

# Invalid Test Topics
pub_invalid_topics = [
    "origin/a/wis2/io-wis2dev-12-test/data",
    "origin/a/wis2/io-wis2dev-12-test/data/core",
#    "origin/a/wis2/io-wis2dev-13-test/metadata/core",
#    "origin/a/wis2/io-wis2dev-13-test/metadata/core/weather",
    "origin/a/wis2/io-wis2dev-14-test/data/core/weather/surface-based-observations",
    "origin/a/wis3/io-wis2dev-15-test/data/core/weather/surface-based-observations/synop",
    "origin/a/wis2/io-wis2dev-15-test/data/core/weather/surface-sed-observations/synop",
    "origin/a/wis3/io-wis2dev-11-test/data/core/weather/surface-based-observations/synop",
    "origin/a/wis2/io-wis2dev-11-test/database/core/weather/surface-based-observations/synop",
    "origin/a/wis2/io-wis2dev-12-test/data/core/weather/surface-based-observations/synop/prediction",
    "origin/a/wis2/io-wis2dev-12-test/data/core/weather/space-based-observations/smm-newton/epic",
    "origin/a/wis2/io-wis2dev-13-test/data/core/weather/space-based-observations/themis-a/scm",
    "origin/a/wis2/io-wis2dev-13-test/data/core/space-weather/space-based-observations/sentinel-2b/msi",
    "origin/a/wis2/io-wis2dev-14-test/data/core/space-weather/space-based-observations/swot/poseidon-3c",
    "origin/a/wis2/io-wis2dev-14-test/data/core/geospatial/surface-based-observations/synop",
    "origin/a/wis2/io-wis2dev-15-test/data/core/ibweather/surface-based-observations/dynop",
    "origin/a/wis2/io-wis2dev-15-test/data/core/atmospheric-composition/satellite",
    "origin/a/wis2/io-wis2dev-12-test/data/core/atmospheric-composition",
    "origin/a/wis2/io-wis2dev-12-test/data/core/weather/prediction",
    "origin/a/wis2/io-wis2dev-13-test/data/core/weather/prediction/analysis",
    "origin/a/wis2/io-wis2dev-13-test/data/core/weather/prediction/analysis/nowcasting",
    "origin/a/wis2/io-wis2dev-14-test/data/core/weather/prediction/hindcast",
    "origin/a/wis2/io-wis2dev-14-test/data/core/weather/prediction/hindcast/short-range",
    "origin/a/wis2/io-wis2dev-15-test/data/core/weather/prediction/hindcast/nowcasting"
]

# Invalid Test Messages
pub_invalid_mesg = [
    {"id": False, "properties": {}},
    {"id": "This is NOT a UUID", "properties": {}},
    {"type": False, "properties": {}},
    {"type": "Not Feature", "properties": {}},
    {"links": [{"href": False }], "properties": {}},
    {"links": [{"rel": False }], "properties": {}},
    {"conformsTo": [False], "properties": {}},
    {"conformsTo": ["This is NOT correct"], "properties": {}},
    {"properties": {"data_id": False }},
    {"properties": {"datetime": False }},
    {"properties": {"datetime": "Not RFC3339 Compliant" }},
    {"properties": {"datetime": False, "end_datetime": "2024-07-20t19:12:29z" }},
    {"properties": {"datetime": False, "start_datetime": "2024-07-20t19:12:29z" }},
    {"properties": {"pubtime": False }},
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
    msg_json['topic'] = msg.topic
    client._userdata['received_messages'].append(msg_json)
    client.message_flag = True

def wait_for_messages(sub_client, num_msgs=0, data_ids=[], max_wait_time=10, min_wait_time=0):
#    pytest.set_trace()
    elapsed_time = 0
    while elapsed_time < max_wait_time:
        if data_ids:
            recv_msgs = [m for m in sub_client._userdata['received_messages'] if m['properties']['data_id'] in data_ids]
        if num_msgs != 0:
            if len(recv_msgs) >= num_msgs and elapsed_time >= min_wait_time:
                print(f"Messages received within {elapsed_time} seconds.")
                break
        time.sleep(message_pace)
        elapsed_time += message_pace

    if elapsed_time >= max_wait_time:
        print(f"Max wait time of {max_wait_time} seconds reached.")
    elif elapsed_time < min_wait_time:
        print(f"Min wait time of {min_wait_time} seconds reached.")
    return recv_msgs


@pytest.fixture
def _setup():
    # Setup
    test_centre_int = random.choice(range(datatest_centres[0], datatest_centres[-1] + 1))
    sub_client = setup_mqtt_client(mqtt_broker_recv)
    for sub_topic in sub_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    test_centre = f"gc_test_centre_{test_centre_int}"
    test_pub_topic = f"config/a/wis2/{test_centre}"
    test_data_id = f"{test_centre}_{uuid.uuid4().hex[:6]}"

    # Capture initial metrics state
    # initial_metrics = get_gc_metrics(prom_host, prom_un, prom_pass, centre_id=test_centre_int)

    # Yield setup data and initial metrics
    setup_dict = {
        "test_centre_int": test_centre_int,
        "sub_client": sub_client,
        "test_centre": test_centre,
        "test_pub_topic": test_pub_topic,
        "test_data_id": test_data_id,
        # "initial_metrics": initial_metrics
    }
    logging.info(f"Setup: {setup_dict}")
    yield setup_dict


def get_gc_metrics(prometheus_baseurl, username, password, centre_id=None):
    """
    Fetches GC metrics from Prometheus.

    Args:
        prometheus_baseurl (str): The base URL of the Prometheus server.
        username (str): The username for Prometheus authentication.
        password (str): The password for Prometheus authentication.
        centre_id (str): The centre ID to filter the metrics by.

    Returns:
        dict: A dictionary containing the fetched metrics.
    """
    print("Fetching GC Metrics")
    report_by = os.getenv('GC_METRICS_REPORT_BY')
    if centre_id is not None:
        centre_id = f'io-wis2dev-{centre_id}-test'
    print(f"Report by: {report_by}")
    metrics_to_fetch = [
        "wmo_wis2_gc_downloaded_total",
        "wmo_wis2_gc_dataserver_status_flag",
        "wmo_wis2_gc_downloaded_last_timestamp_seconds",
        "wmo_wis2_gc_downloaded_errors_total",
        "wmo_wis2_gc_integrity_failed_total"
    ]

    metrics = {}
    for metric_name in metrics_to_fetch:
        result = fetch_prometheus_metrics(metric_name, prometheus_baseurl, username, password, report_by=report_by,
                                          centre_id=centre_id)
        metrics[metric_name] = result
    return metrics

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

def test_1_mqtt_broker_cleartext_connectivity():
    print("\n1. Global Broker Clear-Text Connectivity" + mqtt_broker_clear)
    client = setup_mqtt_client(mqtt_broker_clear, False)
#    with pytest.raises(TimeoutError) as execinfo:
#        setup_mqtt_client(mqtt_broker_clear, False)
#    assert str(execinfo.value) == "Failed to connect to MQTT broker"
    assert not client.connected_flag
    client.disconnect()
    del client
    time.sleep(test_pace)

def test_2_mqtt_broker_tls_connectivity():
    print("\n1. Global Broker TLS Connectivity" + mqtt_broker_tls)
    client = setup_mqtt_client(mqtt_broker_tls, False)
    assert client.connected_flag
    del client
    time.sleep(test_pace)

def test_3_mqtt_broker_ws_connectivity():
    print("\n1. Global Broker WS Connectivity" + mqtt_broker_ws)
    client = setup_mqtt_client(mqtt_broker_ws, False)
    assert client.connected_flag
    del client
    time.sleep(test_pace)

def test_4_mqtt_broker_tls_validate_cert():
    print("\n1. Global Broker TLS Certifiate Validity" + mqtt_broker_tls)
    client = setup_mqtt_client(mqtt_broker_tls, True)
    assert client.connected_flag
    del client
    time.sleep(test_pace)

def test_5_mqtt_broker_ws_validate_cert():
    print("\n1. Global Broker WS Certificate Validity" + mqtt_broker_ws)
    client = setup_mqtt_client(mqtt_broker_ws, True)
    assert client.connected_flag
    del client
    time.sleep(test_pace)

@pytest.mark.parametrize("topic", sub_global_topics)
def test_6_mqtt_broker_subscription_read(topic):
    print("\n2. Global Broker Subscription Read Access")
    client = setup_mqtt_client(mqtt_broker_test, False)
    client.subscribe(topic)
    time.sleep(message_pace)  # Wait for subscription
    assert client.connected_flag
    assert client.subscribed_flag
    client.loop_stop()
    client.disconnect()
    del client
    time.sleep(test_pace)

@pytest.mark.parametrize("topic", pub_write_topics)
def test_7_mqtt_broker_subscription_write(topic):
    print("\n2. Global Broker Write Access Denial")
    client = setup_mqtt_client(mqtt_broker_test, False)
    for sub_topic in pub_general_topics:
        client.subscribe(sub_topic)
    time.sleep(message_pace)  # Wait for subscription
    assert client.connected_flag
    assert client.subscribed_flag
    class PermissionDenied(Exception):
        pass
    with pytest.raises(PermissionDenied) as execinfo:
        pub_result = client.publish(topic, json.dumps(gen_wnm_mesg(topic,"t1t2A1A2iiCCCC_yymmddHHMMSS.bufr")))
        time.sleep(message_pace)
        if len(client._userdata['received_messages']) == 0:
            raise PermissionDenied("Permission for \"everyone:everyone\"")
    client.loop_stop()
    client.disconnect()
    del client
    time.sleep(test_pace)

def test_8_mqtt_broker_antiloop():
    print("\n3. WIS2 Broker Antiloop Test")
    sub_client = setup_mqtt_client(mqtt_broker_test, False)
    sub_client.subscribe("origin/a/wis2/io-wis2dev-12-test/#")
    sub_client.subscribe("origin/a/wis2/io-wis2dev-13-test/#")
    sub_client.subscribe("origin/a/wis2/io-wis2dev-14-test/#")
    sub_client.subscribe("origin/a/wis2/io-wis2dev-15-test/#")
    time.sleep(message_pace)  # Wait for subscription
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    data_id_list = []
    mesg_uuid = str(uuid.uuid4())
    for centreid in [ 12, 13, 14, 15 ]:
        test_data_id = f"wis2dev-{centreid}-test_{uuid.uuid4().hex[:6]}"
        data_id_list.append(test_data_id)
        wnm_scenario_config = {
            "scenario": "wnmtest",
            "configuration": {
                "setup": {
                    "centreid": centreid,
                    "number": 1
                },
                "wnm": {
                    "id": mesg_uuid,
                    "properties": {
                        "data_id": test_data_id,
                        "pubtime": "2024-09-23T11:37:12Z",
                        "datetime": "2024-09-23T11:37:12Z"
                    }
                }
            }
        }
        print(f"Scenario message: {json.dumps(wnm_scenario_config, indent=4)}")
        pub_client = setup_mqtt_client(mqtt_broker_trigger, False)
        pub_client.publish("config/a/wis2", json.dumps(wnm_scenario_config))
        time.sleep(message_pace)  # Wait for messages
    assert len(wait_for_messages(sub_client, 1, data_id_list, 10, 1)) == 1
    assert sub_client.message_flag
    sub_client.loop_stop()
    sub_client.disconnect()
    pub_client.loop_stop()
    pub_client.disconnect()
    del sub_client
    del pub_client
    time.sleep(test_pace)

def test_9_node_invalid_centre_id_test():
    print("\n4. WIS2 Node Invalid Centre ID Test")
    sub_client = setup_mqtt_client(mqtt_broker_test, False)
    sub_client.subscribe("origin/a/wis2/io-wis2dev-12-test/#")
    time.sleep(message_pace)  # Wait for subscription
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    test_data_id = f"wis2dev-12-test_{uuid.uuid4().hex[:6]}"
    wnm_scenario_config = {
        "scenario": "wnmtest",
        "configuration": {
            "setup": {
                "centreid": 12,
                "topic": pub_valid_topics[4],
                "number": 1
            },
            "wnm": {
                "properties": { 
                    "data_id": test_data_id
                }
            }
        }
    }
    print(f"Scenario message: {json.dumps(wnm_scenario_config, indent=4)}")
    pub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    pub_client.publish("config/a/wis2", json.dumps(wnm_scenario_config))
    time.sleep(message_pace)  # Wait for messages
    assert len(wait_for_messages(sub_client, 1, [test_data_id], 10, 1)) == 0
    sub_client.loop_stop()
    sub_client.disconnect()
    pub_client.loop_stop()
    pub_client.disconnect()
    del sub_client
    del pub_client
    time.sleep(test_pace)

def test_10_valid_topic_test():
    print("\n4. WIS2 GB Valid Topic Test")
    sub_client = setup_mqtt_client(mqtt_broker_test, False)
    sub_client.subscribe(f"origin/a/wis2/#")
    time.sleep(message_pace)  # Wait for messages
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    pub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    mesg_count = 0
    data_id_list = []
    for topic in pub_valid_topics:
        cent_id_num = center_id_regex.search(topic).group(1)
        data_id_list.append(f"wis2dev-{cent_id_num}-test_{uuid.uuid4().hex[:6]}")
        wnm_scenario_config = {
            "scenario": "wnmtest",
            "configuration": {
                "setup": {
                    "centreid": cent_id_num,
                    "topic": topic,
                    "number": 1
                 },
                 "wnm": {
                     "properties": { 
                     "data_id": data_id_list[mesg_count]
                     }
                 }
            }
        }
        print(f"Scenario message: {json.dumps(wnm_scenario_config, indent=4)}")
        mesg_count += 1
        pub_client.publish("config/a/wis2", json.dumps(wnm_scenario_config))
        time.sleep(message_pace)
    assert len(wait_for_messages(sub_client, 1, data_id_list, 10, 1)) == mesg_count
    assert sub_client.message_flag
    sub_client.loop_stop()
    sub_client.disconnect()
    pub_client.loop_stop()
    pub_client.disconnect()
    del sub_client
    del pub_client
    time.sleep(test_pace)
    
def test_11_valid_msg_test():
    print("\n4. WIS2 GB Valid Message Test")
    sub_client = setup_mqtt_client(mqtt_broker_test, False)
    sub_client.subscribe(f"origin/a/wis2/#")
    pub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    time.sleep(message_pace)  # Wait for messages
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    mesg_count = 0
    data_id_list = []
    for topic in pub_valid_topics:
        cent_id_num = center_id_regex.search(topic).group(1)
        data_id_list.append(f"wis2dev-{cent_id_num}-test_{uuid.uuid4().hex[:6]}")
        wnm_scenario_config = {
           "scenario": "wnmtest",
           "configuration": {
               "setup": {
                   "centreid": cent_id_num,
                   "topic": topic,
                   "number": 1
                },
                 "wnm": {
                     "properties": { 
                         "data_id": data_id_list[mesg_count]
                     }
                 }
            }
        }
        print(f"Scenario message: {json.dumps(wnm_scenario_config, indent=4)}")
        mesg_count += 1
        pub_client.publish(f"config/a/wis2", json.dumps(wnm_scenario_config))
        time.sleep(message_pace)
    time.sleep(message_pace * 10)  # Wait for messages
    assert len(wait_for_messages(sub_client, 1, data_id_list, 10, 1)) == mesg_count
    assert sub_client.message_flag
    sub_client.loop_stop()
    sub_client.disconnect()
    pub_client.loop_stop()
    pub_client.disconnect()
    del sub_client
    del pub_client
    time.sleep(test_pace)
    
def test_12_invalid_topic_test():
    print("\n4. WIS2 GB Inalid Topic Test")
    sub_client = setup_mqtt_client(mqtt_broker_test, False)
    sub_client.subscribe(f"origin/a/wis2/#")
    pub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    time.sleep(message_pace)  # Wait for messages
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    mesg_count = 0
    data_id_list = []
    for topic in pub_invalid_topics:
        cent_id_num = center_id_regex.search(topic).group(1)
        data_id_list.append(f"wis2dev-{cent_id_num}-test_{uuid.uuid4().hex[:6]}")
        wnm_scenario_config = {
            "scenario": "wnmtest",
            "configuration": {
                "setup": {
                    "centreid": cent_id_num,
                    "topic": topic,
                    "number": 1
                 },
                 "wnm": {
                     "properties": { 
                         "data_id": data_id_list[mesg_count]
                     }
                 }
            }
        }
        print(f"Scenario message: {json.dumps(wnm_scenario_config, indent=4)}")
        mesg_count += 1
        pub_client.publish("config/a/wis2", json.dumps(wnm_scenario_config))
        time.sleep(message_pace)
    assert len(wait_for_messages(sub_client, 1, data_id_list, 10, 1)) == 0
    sub_client.loop_stop()
    sub_client.disconnect()
    pub_client.loop_stop()
    pub_client.disconnect()
    del sub_client
    del pub_client
    time.sleep(test_pace)
    
def test_13_invalid_msg_test():
    print("\n4. WIS2 GB Inalid Message Test")
    sub_client = setup_mqtt_client(mqtt_broker_test, False)
    sub_client.subscribe(f"origin/a/wis2/io-wis2dev-12-test/#")
    pub_client = setup_mqtt_client(mqtt_broker_trigger, False)
    time.sleep(message_pace)  # Wait for messages
    assert sub_client.connected_flag
    assert sub_client.subscribed_flag
    mesg_count = 0
    data_id_list = []
    for mesg in pub_invalid_mesg:
        if "data_id" not in mesg['properties']:
            mesg['properties']['data_id'] = f"wis2dev-12-test_{uuid.uuid4().hex[:6]}"
            data_id_list.append(mesg['properties']['data_id'])
        wnm_scenario_config = {
           "scenario": "wnmtest",
           "configuration": {
              "setup": {
                 "centreid": 12,
                 "number": 1
              },
              "wnm": mesg
           }
        }
        print(f"Scenario message: {json.dumps(wnm_scenario_config, indent=4)}")
        mesg_count += 1
        pub_client.publish(f"config/a/wis2", json.dumps(wnm_scenario_config))
        time.sleep(message_pace)
    assert len(wait_for_messages(sub_client, 1, data_id_list, 10, 1)) == 0
    sub_client.loop_stop()
    sub_client.disconnect()
    pub_client.loop_stop()
    pub_client.disconnect()
    del sub_client
    del pub_client
    time.sleep(test_pace)
