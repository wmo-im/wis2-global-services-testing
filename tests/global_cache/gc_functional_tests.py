import json
import uuid
import random
import sys
import os

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
mqtt_broker_out = os.getenv('MQTT_BROKER_OUT')
mqtt_broker_in = os.getenv('MQTT_BROKER_IN')
mqtt_broker_gc = os.getenv('MQTT_BROKER_GC')
# Topics
sub_topics = [
    "origin/a/wis2/#",
    "cache/a/wis2/#",

]
pub_topics = [
    "origin/a/wis2/testcentre1/data/core/somecategory/123123123",
    "origin/a/wis2/testcentre2/data/core/somecategory3/3333",
    "origin/a/wis2/testcentre3/data/core/somecategory4/1123233322",
    # "cache/a/wis2/testcentre1/metadata/somecategory/sometype",
]

# Initialize MQTT client
rand_id = "wis2_testing" + str(uuid.uuid4())[:10]


# Helper functions

# get random topic
def get_random_topic():
    # select a random topic from below, and fill in the wildcards for a complete topic
    topics = ["origin/a/wis2/+/data/#", "cache/a/wis2/+/data/#", "origin/a/wis2/+/metadata/#",
              "cache/a/wis2/+/metadata/#"]
    # get random
    topic = topics[random.randint(0, len(topics) - 1)]
    # fill in the wildcards
    topic = topic.replace("+", str(uuid.uuid4()))
    topic = topic.replace("#", str(uuid.uuid4()))
    return topic


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


def setup_mqtt_client(connection_info: str):
    client = mqtt.Client(client_id=rand_id, protocol=mqtt.MQTTv5, userdata={'received_messages': []})
    client.on_connect = flag_on_connect
    client.on_subscribe = flag_on_subscribe
    client.on_message = flag_on_message
    connection_info = urlparse(connection_info)
    client.username_pw_set(connection_info.username, connection_info.password)
    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = 300  # seconds
    client.tls_set()
    client.connect(host=connection_info.hostname, port=connection_info.port, properties=properties)
    client.loop_start()
    time.sleep(1)  # Wait for connection
    if not client.is_connected():
        raise Exception("Failed to connect to MQTT broker")
    return client


def generate_wnm(topic: str = None, msg_id: str = None, msg_dt: datetime = None, url: str = None,
                 content_type: str = None, msg_props: dict = None):
    topic = topic or get_random_topic()
    msg_dt = msg_dt.strftime('%Y-%m-%dT%H:%M:%S') + 'Z' if msg_dt is not None else datetime.utcnow().strftime(
        '%Y-%m-%dT%H:%M:%S') + 'Z'
    # msg_dt = msg_dt if msg_dt is not None else datetime.utcnow()
    message_args = {
        'topic': topic,
        'content_type': content_type,
        'url': "https://wis2-global-cache.s3.amazonaws.com/br-inmet/data/core/weather/surface-based-observations/synop/WIGOS_0-76-0-3106200000000597_20240822T140000.bufr4",
        'identifier': msg_id or str(uuid.uuid4()),
        'pubtime': msg_dt,  #
        # 'geometry': [33.8, -11.8, 123],
        # 'metadata_id': 'mock/metadata/identifier',
        # 'wigos_station_identifier': '0-20000-12345',
        # 'operation': 'create'
    }
    if msg_props:
        message_args.update(msg_props)
    message = create_message(**message_args)
    return topic, message


def test_1_mqtt_broker_connectivity():
    print("\n1. MQTT Broker Connectivity")
    assert mqtt_helpers.check_broker_connectivity(mqtt_broker_gc) is True

@pytest.mark.parametrize("topic", [
    "cache/a/wis2/+/data/core/#",
    "cache/a/wis2/+/metadata/#"
])
def test_2_mqtt_broker_subscription(topic):
    print("\n2. GC MQTT Broker Subscription")
    print(f"Subscribing to topic: {topic}")
    # use pywispubsub client but specify the on_connect, on_subscribe callbacks
    client = MQTTPubSubClient(mqtt_broker_gc)
    client.conn.subscribed_flag = False
    client.conn.on_subscribe = flag_on_subscribe
    client.conn.on_connect = flag_on_connect
    client.conn.loop_start()
    result, mid = client.conn.subscribe(topic)
    time.sleep(1)  # Wait for subscription
    assert result is mqtt.MQTT_ERR_SUCCESS
    assert client.conn.subscribed_flag is True
    client.conn.loop_stop()
    client.conn.disconnect()
    del client

# @pytest.mark.parametrize("pub_topic", pub_topics)
def test_3_mqtt_broker_message_flow():
    print("\n3. WIS2 Notification Message (WNM) Processing")
    # generate some random id's for the messages
    sub_client = setup_mqtt_client(mqtt_broker_out)
    for sub_topic in sub_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    test_3_centre = f"centre_{uuid.uuid4().hex[:6]}"
    test_3_pub_topic = f"config/a/wis2/{test_3_centre}"
    test_3_data_id = f"somedataid1234_{test_3_centre}"
    # generate RFC3339 datetime
    test_3_dt = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    # todo - trigger WNM's from the message generator, rather than generate here
    # wnm = generate_wnm(pub_topic)
    wnm_dataset_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid_min": 15,
                "centreid_max": 15,
                "number": 5,
                "size_min": 128,
                "size_max": 512
            },
            "wnm": {
                "properties": {
                    # "data_id": test_3_data_id,
                    # "pubtime": "2024-08-23T22:41:59Z"
                }
            }
        }
    }
    print(wnm_dataset_config)
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # publish the message
    # unique id is data_id+pubtime
    # client.publish(m[0], json.dumps(m[1]), qos=1)
    # pub_client.pub(topic=pub_topic, message=json.dumps(wnm[1]))
    pub_client.pub(topic=test_3_pub_topic, message=json.dumps(wnm_dataset_config))
    # print(f"Published message with data_id: {wnm_dataset_config['configuration']['wnm']['properties']['data_id']}")
    # sent_messages.append(wnm[1])
    # muid = "|".join([wnm[1]['properties']['data_id'], wnm[1]['properties']['pubtime']])
    # print(f"Published message with muid: {muid}")
    time.sleep(10)  # Wait for messages
    origin_msgs = [m for m in sub_client._userdata['received_messages'] if "origin" in m['topic']]
    cache_msgs = [m for m in sub_client._userdata['received_messages'] if "cache" in m['topic']]
    sub_client.loop_stop()
    sub_client.disconnect()
    assert len(origin_msgs) > 0
    assert len(cache_msgs) > 0

    # compare origin and cache messages

    for origin_msg in origin_msgs:
        # match based on data_id and pubtime
        cache_msg = [m for m in cache_msgs if
                     m['properties']['data_id'] == origin_msg['properties']['data_id'] and m['properties'][
                         'pubtime'] == origin_msg['properties']['pubtime']]
        assert len(cache_msg) == 1
        cache_msg = cache_msg[0]
        # assert the msg id's are different
        assert cache_msg['id'] != origin_msg['id']
        # assert the links['rel']='canonical' are different
        # get the index of the link with rel=canonical
        can_i_cache = [i for i, l in enumerate(cache_msg['links']) if l['rel'] == 'canonical'][0]
        can_i_origin = [i for i, l in enumerate(origin_msg['links']) if l['rel'] == 'canonical'][0]
        assert cache_msg['links'][can_i_cache]['href'] != origin_msg['links'][can_i_origin]['href']
         # use pywispubsub to validate the cache messages
        is_valid, errors = validate_message(cache_msg)
        assert is_valid is True
        # verification
        # todo - verify_data is not working as expected
        # verified = verify_data(cache_msg, verify_certs=False)
        # assert verified is True

def test_4_cache_false_directive():
    print("\n4. Cache False Directive")
    # generate some random id's for the messages
    sub_client = setup_mqtt_client(mqtt_broker_out)
    for sub_topic in sub_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    test_centre = f"centre_{uuid.uuid4().hex[:6]}"
    test_pub_topic = f"config/a/wis2/{test_centre}"
    wnm_dataset_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid_min": 15,
                "centreid_max": 15,
                "number": 5,
                "size_min": 16,
                "size_max": 128
            },
            "wnm": {
                "properties": {
                    "cache": False,
                }
            }
        }
    }
    print(wnm_dataset_config)
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # publish the message
    # unique id is data_id+pubtime
    # client.publish(m[0], json.dumps(m[1]), qos=1)
    # pub_client.pub(topic=pub_topic, message=json.dumps(wnm[1]))
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_dataset_config))
    # print(f"Published message with data_id: {wnm_dataset_config['configuration']['wnm']['properties']['data_id']}")
    # sent_messages.append(wnm[1])
    # muid = "|".join([wnm[1]['properties']['data_id'], wnm[1]['properties']['pubtime']])
    # print(f"Published message with muid: {muid}")
    time.sleep(10)  # Wait for messages
    origin_msgs = [m for m in sub_client._userdata['received_messages'] if "origin" in m['topic']]
    cache_msgs = [m for m in sub_client._userdata['received_messages'] if "cache" in m['topic']]
    sub_client.loop_stop()
    sub_client.disconnect()
    assert len(origin_msgs) > 0
    assert len(cache_msgs) > 0

    # compare origin and cache messages

    for origin_msg in origin_msgs:
        # match based on data_id and pubtime
        cache_msg = [m for m in cache_msgs if
                     m['properties']['data_id'] == origin_msg['properties']['data_id'] and m['properties'][
                         'pubtime'] == origin_msg['properties']['pubtime']]
        assert len(cache_msg) > 0
        cache_msg = cache_msg[0]
        # assert the msg id's are different
        assert cache_msg['id'] != origin_msg['id']
        # assert the links['rel']='canonical' are the SAME
        can_i_cache = [i for i, l in enumerate(cache_msg['links']) if l['rel'] == 'canonical'][0]
        can_i_origin = [i for i, l in enumerate(origin_msg['links']) if l['rel'] == 'canonical'][0]
        assert cache_msg['links'][can_i_cache]['href'] == origin_msg['links'][can_i_origin]['href']
         # use pywispubsub to validate the cache messages
        is_valid, errors = validate_message(cache_msg)
        assert is_valid is True
        # verification
        # todo - verify_data is not working as expected
        # verified = verify_data(cache_msg, verify_certs=False)
        # assert verified is True
        # todo - verify metrics
        """
        GC Metrics
            wmo_wis2_gc_download_total (unchanged)
            wmo_wis2_gc_dataserver_status_flag (unchanged)
            wmo_wis2_gc_dataserver_last_download_timestamp_seconds (unchanged)
            wmo_wis2_gc_no_cache_total (+=1 for each WNM)
        """