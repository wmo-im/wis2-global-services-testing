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
                "centreid_min": 13,
                "centreid_max": 13,
                "number": 1,
                "size_min": 128,
                "size_max": 512
            },
            "wnm": {
                "properties": {
                    "data_id": test_3_data_id,
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
        verified = verify_data(cache_msg, verify_certs=False)
        assert verified is True

def test_4_cache_false_directive():
    print("\n4. Cache False Directive")
    # generate some random id's for the messages
    sub_client = setup_mqtt_client(mqtt_broker_out)
    for sub_topic in sub_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    test_centre = f"centre_{uuid.uuid4().hex[:6]}"
    # always use the same topic for the msg generator config/a/wis2/#
    test_pub_topic = f"config/a/wis2/{test_centre}"
    wnm_dataset_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid_min": 14,
                "centreid_max": 14,
                "number": 5,
                "size_min": 16,
                "size_max": 128000
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
    time.sleep(5)  # Wait for messages
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


def test_5_source_download_failure():
    print("\n5. Source Download Failure")
    # generate some random id's for the messages
    sub_client = setup_mqtt_client(mqtt_broker_out)
    for sub_topic in sub_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    test_centre = f"centre_{uuid.uuid4().hex[:6]}"
    # always use the same topic for the msg generator config/a/wis2/#
    test_pub_topic = f"config/a/wis2/{test_centre}"
    test_data_id = f"somedataid1234_{test_centre}"
    test_dt = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

    # Prepare WNM with invalid data download link
    wnm_dataset_config = {
        "scenario": "wnmtest",
        "configuration": {
            "setup": {
                "centreid_min": 11,
                "centreid_max": 11,
                "number": 1,
                "size_min": 128,
                "size_max": 256
            },
            "wnm": {
                "properties": {
                    "data_id": test_data_id,
                    # "pubtime": test_dt,
                    "links": [
                        {
                            "href": "https://www.example.org/random",
                            "rel": "canonical"
                        }
                    ]
                }
            }
        }
    }
    print(wnm_dataset_config)
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # Publish the message
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_dataset_config))
    time.sleep(10)  # Wait for messages

    # Evaluate
    origin_msgs = [m for m in sub_client._userdata['received_messages'] if "origin" in m['topic']]
    cache_msgs = [m for m in sub_client._userdata['received_messages'] if "cache" in m['topic']]
    sub_client.loop_stop()
    sub_client.disconnect()

    # Origin Messages
    assert len(origin_msgs) > 0
    # No messages should be published on the cache/a/wis2/# topic
    for origin_msg in origin_msgs:
        # match based on data_id and pubtime
        cache_msg = [m for m in cache_msgs if
                     m['properties']['data_id'] == origin_msg['properties']['data_id'] and m['properties'][
                         'pubtime'] == origin_msg['properties']['pubtime']]
        assert len(cache_msg) == 0

    # GC Metrics
    # Assuming a function get_gc_metrics() that retrieves the GC metrics
    # metrics = get_gc_metrics()
    # assert metrics['wmo_wis2_gc_dataserver_status_flag'] == 0
    # assert metrics['wmo_wis2_gc_downloaded_errors_total'] > 0

def test_6_cache_override():
    print("\n6. Cache Override (Optional)")
    pass
    # generate some random id's for the messages
    sub_client = setup_mqtt_client(mqtt_broker_out)
    for sub_topic in sub_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    test_centre = f"centre_{uuid.uuid4().hex[:6]}"
    # always use the same topic for the msg generator config/a/wis2/#
    test_pub_topic = f"config/a/wis2/{test_centre}"
    test_data_id = f"somedataid1234_{test_centre}"
    # test_dt = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

    # Prepare WNM with properties that trigger the cache override directive
    wnm_dataset_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid_min": 16,
                "centreid_max": 16,
                "number": 1,
                "size_min": 128,
                "size_max": 512
            },
            "wnm": {
                "properties": {
                    "data_id": test_data_id,
                }
            }
        }
    }
    print(wnm_dataset_config)
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # Publish the message
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_dataset_config))
    time.sleep(10)  # Wait for messages

    # Evaluate
    origin_msgs = [m for m in sub_client._userdata['received_messages'] if "origin" in m['topic']]
    cache_msgs = [m for m in sub_client._userdata['received_messages'] if "cache" in m['topic']]
    sub_client.loop_stop()
    sub_client.disconnect()

    # Origin Messages
    assert len(origin_msgs) > 0
    # No messages should be published on the cache/a/wis2/# topic
    for origin_msg in origin_msgs:
        # match based on data_id and pubtime
        cache_msg = [m for m in cache_msgs if
                     m['properties']['data_id'] == origin_msg['properties']['data_id'] and m['properties'][
                         'pubtime'] == origin_msg['properties']['pubtime']]
        assert len(cache_msg) == 0

    # GC Metrics
    # Assuming a function get_gc_metrics() that retrieves the GC metrics
    # metrics = get_gc_metrics()
    # assert metrics['wmo_wis2_gc_cache_override_total'] > 0
    # assert metrics['wmo_wis2_gc_download_total'] == 0
    # assert metrics['wmo_wis2_gc_dataserver_status_flag'] == 0
    # assert metrics['wmo_wis2_gc_dataserver_last_download_timestamp_seconds'] == 0
    # assert metrics['wmo_wis2_gc_downloaded_errors_total'] == 0


def test_7_data_integrity_check_failure():
    print("\n7. Data Integrity Check Failure (Recommended)")
    num_origin_msgs = 1
    sub_client = setup_mqtt_client(mqtt_broker_out)
    for sub_topic in sub_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    test_centre = f"centre_{uuid.uuid4().hex[:6]}"
    # always use the same topic for the msg generator config/a/wis2/#
    test_pub_topic = f"config/a/wis2/{test_centre}"
    test_data_id = f"somedataid1234_{test_centre}"
    test_dt = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

    # Prepare WNM with invalid data integrity value
    wnm_dataset_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid_min": 12,
                "centreid_max": 12,
                "number": num_origin_msgs,
                "size_min": 128,
                "size_max": 512
            },
            "wnm": {
                "properties": {
                    "data_id": test_data_id,
                    # "pubtime": "2024-08-23T22:41:59Z",
                    "integrity": {
                        "value": "invalid_integrity_value",
                        "method": "sha512"
                    }
                }
            }
        }
    }
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # Publish the message
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_dataset_config))
    time.sleep(5)  # Wait for messages

    # Evaluate
    origin_msgs = [m for m in sub_client._userdata['received_messages'] if "origin" in m['topic']]
    cache_msgs = [m for m in sub_client._userdata['received_messages'] if "cache" in m['topic']]
    sub_client.loop_stop()
    sub_client.disconnect()

    # Origin Messages
    assert len(origin_msgs) == num_origin_msgs
    # No messages should be published on the cache/a/wis2/# topic
    assert len(cache_msgs) == 0

    # GC Metrics
    # metrics = get_gc_metrics()
    # assert metrics['wmo_wis2_gc_download_total'] == 0
    # assert metrics['wmo_wis2_gc_dataserver_status_flag'] == 0
    # assert metrics['wmo_wis2_gc_dataserver_last_download_timestamp_seconds'] == 0
    # assert metrics['wmo_wis2_gc_downloaded_errors_total'] > 0
    # assert metrics['wmo_wis2_gc_integrity_failed_total'] > 0

@pytest.mark.parametrize("centre_id", [11, 12, 13])
def test_8_wnm_deduplication(centre_id):
    print("\n8. WIS2 Notification Message Deduplication")
    num_origin_msgs = 5
    sub_client = setup_mqtt_client(mqtt_broker_out)
    for sub_topic in sub_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    test_centre = f"centre_{centre_id}_{uuid.uuid4().hex[:6]}"
    # always use the same topic for the msg generator config/a/wis2/#
    test_pub_topic = f"config/a/wis2/{test_centre}"
    test_data_id = f"somedataid1234_{test_centre}"
    # test_dt = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

    # Prepare WNM with duplicate properties
    wnm_dataset_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid_min": centre_id,
                "centreid_max": centre_id,
                "number": num_origin_msgs,
                "size_min": 1024*20,
                "size_max": 1024*30
            },
            "wnm": {
                "properties": {
                    "data_id": test_data_id,
                }
            }
        }
    }
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # Publish the message twice
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_dataset_config))
    # disconnect the client
    pub_client.close()
    # pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_dataset_config))
    time.sleep(7)  # Wait for messages

    # Evaluate
    cache_msgs = [m for m in sub_client._userdata['received_messages'] if "cache" in m['topic']]
    origin_msgs = [m for m in sub_client._userdata['received_messages'] if "origin" in m['topic']]
    sub_client.loop_stop()
    sub_client.disconnect()

    # Only one message should be published on the cache/a/wis2/# topic
    assert len(origin_msgs) == num_origin_msgs
    assert len(cache_msgs) == 1

    # GC Metrics
    # metrics = get_gc_metrics()
    # assert metrics['wmo_wis2_gc_download_total'] == 1
    # assert metrics['wmo_wis2_gc_dataserver_status_flag'] == 1
    # assert metrics['wmo_wis2_gc_downloaded_errors_total'] == 0
    # assert metrics['wmo_wis2_gc_integrity_failed_total'] == 0

def test_8_1_wnm_deduplication_alternative_1():
    print("\n8.1. WIS2 Notification Message Deduplication (Alternative 1)")
    sub_client = setup_mqtt_client(mqtt_broker_out)
    for sub_topic in sub_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    test_centre = f"centre_{uuid.uuid4().hex[:6]}"
    test_pub_topic = f"config/a/wis2/{test_centre}"
    test_data_id = f"somedataid1234_{test_centre}"
    test_dt = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

    # Prepare WNM with invalid and valid properties
    wnm_invalid_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid_min": 16,
                "centreid_max": 16,
                "number": 1,
                "size_min": 10000,
                "size_max": 11000
            },
            "wnm": {
                "properties": {
                    "data_id": test_data_id,
                    "pubtime": test_dt,
                    "links": [
                        {
                            "rel": "canonical",
                            "href": "http://invalid.example.com/data"
                        }
                    ]
                }
            }
        }
    }
    wnm_valid_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid_min": 16,
                "centreid_max": 16,
                "number": 1,
                "size_min": 10000,
                "size_max": 11000
            },
            "wnm": {
                "properties": {
                    "data_id": test_data_id,
                    "pubtime": test_dt,
                    "links": [
                        {
                            "rel": "canonical",
                            "href": "http://example.com/data"
                        }
                    ]
                }
            }
        }
    }
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # Publish the invalid message first, then the valid message
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_invalid_config))
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_valid_config))
    time.sleep(10)  # Wait for messages

    # Evaluate
    cache_msgs = [m for m in sub_client._userdata['received_messages'] if "cache" in m['topic']]
    sub_client.loop_stop()
    sub_client.disconnect()

    # Only one message should be published on the cache/a/wis2/# topic
    assert len(cache_msgs) == 1

    # GC Metrics
    metrics = get_gc_metrics()
    assert metrics['wmo_wis2_gc_download_total'] == 1
    assert metrics['wmo_wis2_gc_dataserver_status_flag'] == 1
    assert metrics['wmo_wis2_gc_downloaded_errors_total'] == 1
    assert metrics['wmo_wis2_gc_integrity_failed_total'] == 0

def test_8_2_wnm_deduplication_alternative_2():
    print("\n8.2. WIS2 Notification Message Deduplication (Alternative 2)")
    sub_client = setup_mqtt_client(mqtt_broker_out)
    for sub_topic in sub_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    test_centre = f"centre_{uuid.uuid4().hex[:6]}"
    test_pub_topic = f"config/a/wis2/{test_centre}"
    test_data_id = f"somedataid1234_{test_centre}"
    test_dt_1 = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    test_dt_2 = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

    # Prepare WNM with decreasing pubtime
    wnm_config_1 = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid_min": 16,
                "centreid_max": 16,
                "number": 1,
                "size_min": 10000,
                "size_max": 11000
            },
            "wnm": {
                "properties": {
                    "data_id": test_data_id,
                    "pubtime": test_dt_1,
                    "links": [
                        {
                            "rel": "canonical",
                            "href": "http://example.com/data"
                        }
                    ]
                }
            }
        }
    }
    wnm_config_2 = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid_min": 16,
                "centreid_max": 16,
                "number": 1,
                "size_min": 10000,
                "size_max": 11000
            },
            "wnm": {
                "properties": {
                    "data_id": test_data_id,
                    "pubtime": test_dt_2,
                    "links": [
                        {
                            "rel": "canonical",
                            "href": "http://example.com/data"
                        }
                    ]
                }
            }
        }
    }
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # Publish the message with later pubtime first, then the earlier pubtime
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_config_1))
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_config_2))
    time.sleep(10)  # Wait for messages

    # Evaluate
    cache_msgs = [m for m in sub_client._userdata['received_messages'] if "cache" in m['topic']]
    sub_client.loop_stop()
    sub_client.disconnect()

    # Both messages should be published on the cache/a/wis2/# topic
    assert len(cache_msgs) == 2

    # GC Metrics
    metrics = get_gc_metrics()
    assert metrics['wmo_wis2_gc_download_total'] == 2
    assert metrics['wmo_wis2_gc_dataserver_status_flag'] == 1
    assert metrics['wmo_wis2_gc_downloaded_errors_total'] == 0
    assert metrics['wmo_wis2_gc_integrity_failed_total'] == 0