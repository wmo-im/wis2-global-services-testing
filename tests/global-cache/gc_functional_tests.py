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
# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared_utils import mqtt_helpers


# Connection strings for the development global broker and message generator
mqtt_broker_out = "mqtts://everyone:everyone@dev-cache.wis2.synopticdata.com:8883"
mqtt_broker_in = "mqtts://everyone:everyone@emqx.wis2.synopticdata.com:8883"

# Topics
sub_topics = [
    "cache/a/wis2/#",
    # "origin/a/wis2/#",
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
    # print("Subscribed with mid " + str(mid) + " and QoS " + str(granted_qos))
    client.subscribed_flag = True


def flag_on_message(client, userdata, msg):
    print(f"Received message on topic {msg.topic} with payload {msg.payload}")
    client._userdata['received_messages'].append(msg.payload.decode())


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
    time.sleep(.1)  # Wait for connection
    if not client.connected_flag:
        raise Exception("Failed to connect to MQTT broker")
    return client


def test_1_gc_mqtt_broker_connectivity():
    print("\n1. MQTT Broker Connectivity")
    assert mqtt_helpers.check_broker_connectivity(mqtt_broker_out) is True


@pytest.mark.parametrize("topic", [
    "cache/a/wis2/+/data/core/#",
    "cache/a/wis2/+/metadata/#"
])
def test_2_gc_mqtt_broker_subscription(topic):
    print("\n2. GC MQTT Broker Subscription")
    print(f"Subscribing to topic: {topic}")

    client = setup_mqtt_client(mqtt_broker_out)
    client.subscribed_flag = False
    result, mid = client.subscribe(topic)
    time.sleep(.1)  # Wait for subscription
    assert result is mqtt.MQTT_ERR_SUCCESS
    assert client.subscribed_flag is True
    client.loop_stop()
    client.disconnect()
    del client

@pytest.mark.parametrize("topic", [
    "cache/a/wis2/+/data/core/#",
    "cache/a/wis2/+/metadata/#"
])
def test_2test_gc_mqtt_broker_subscription(topic):
    print("\n2. GC MQTT Broker Subscription")
    print(f"Subscribing to topic: {topic}")
    # use pywispubsub client but specify the on_connect, on_subscribe callbacks
    client = MQTTPubSubClient(mqtt_broker_out)
    client.subscribed_flag = False
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


def generate_wnm(topic: str = None, msg_id: str = None, msg_dt: datetime = None, url: str = None,
                 content_type: str = None, msg_props: dict = None):
    topic = topic or get_random_topic()
    msg_dt = msg_dt.strftime('%Y-%m-%dT%H:%M:%S') + 'Z' if msg_dt is not None else datetime.utcnow().strftime(
        '%Y-%m-%dT%H:%M:%S') + 'Z'
    # msg_dt = msg_dt if msg_dt is not None else datetime.utcnow()
    message_args = {
        'topic': topic,
        'content_type': content_type,
        'url': "https://wis2-global-cache.s3.amazonaws.com/us-noaa-synoptic/data/core/weather/surface-based-observations/synop/WIGOS_0-840-0-KSEM_20240808T132000.bufr4",
        'identifier': msg_id or str(uuid.uuid4()),
        'datetime_': msg_dt,  #
        # 'geometry': [33.8, -11.8, 123],
        # 'metadata_id': 'mock/metadata/identifier',
        # 'wigos_station_identifier': '0-20000-12345',
        # 'operation': 'create'
    }
    if msg_props:
        message_args.update(msg_props)
    message = create_message(**message_args)
    return topic, message


@pytest.mark.parametrize("pub_topic", pub_topics)
def test_mqtt_broker_message_flow(pub_topic):
    print("\n3. WIS2 Notification Message (WNM) Processing")
    # generate some random id's for the messages
    sub_client = setup_mqtt_client(mqtt_broker_out)
    # client = mqtt.Client(client_id=rand_id, protocol=mqtt.MQTTv5, userdata={'received_messages': []})
    # sub_client.on_connect = flag_on_connect
    # sub_client.on_subscribe = flag_on_subscribe
    # sub_client.on_message = flag_on_message
    sub_client.subscribed_flag = False
    for t in sub_topics:
        sub_client.subscribe(t, qos=1)
    sub_client.subscribe("cache/a/wis2/#", qos=1)
    # time.sleep(1)  # Wait for subscription
    # assert client.subscribed_flag == True

    sent_messages = []
    # add random salt to pubtopic, 6 hex characters
    pub_topic = "/".join([pub_topic + uuid.uuid4().hex[:6]])
    wnm = generate_wnm(pub_topic)
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # publish the message
    # unique id is data_id+datetime
    # client.publish(m[0], json.dumps(m[1]), qos=1)
    pub_client.pub(topic=pub_topic, message=json.dumps(wnm[1]))
    sent_messages.append(wnm[1])
    muid = "|".join([wnm[1]['properties']['data_id'], wnm[1]['properties']['datetime']])
    print(f"Published message with muid: {muid}")
    time.sleep(10)  # Wait for messages
    received_msgs = [json.loads(msg) for msg in sub_client._userdata['received_messages']]
    sub_client.loop_stop()
    sub_client.disconnect()

    # evaluate
    for origin_msg in sent_messages:
        # match based on data_id and datetime
        cache_msg = [m for m in received_msgs if
                     m['properties']['data_id'] == origin_msg['properties']['data_id'] and m['properties'][
                         'datetime'] == origin_msg['properties']['datetime']]
        assert len(cache_msg) == 1
        cache_msg = cache_msg[0]
        # assert the msg id's are different
        assert cache_msg['id'] != origin_msg['id']
        # assert the links['rel']='canonical' are different
        assert cache_msg['links'][0]['href'] != origin_msg['links'][0]['href']
         # use pywispubsub to validate the cache messages
        is_valid, errors = validate_message(cache_msg)
        assert is_valid is True
        # verification
        verified = verify_data(cache_msg)
        assert verified is True
