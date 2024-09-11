import json
import logging
import uuid
import random
import sys
import os
from copy import deepcopy

import pytest
import paho.mqtt.client as mqtt
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from pywis_pubsub.validation import validate_message
from pywis_pubsub.verification import verify_data
from pywis_pubsub.mqtt import MQTTPubSubClient
from dotenv import load_dotenv

from tests.shared_utils.prom_metrics import fetch_prometheus_metrics

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared_utils import mqtt_helpers, ab, prom_metrics

datatest_centres = [11, 20]
ab_centres = [1001, 1020]

# Connection strings for the development global broker and message generator
# Access the environment variables
load_dotenv("../default.env")
load_dotenv("../secrets.env")
mqtt_broker_out = os.getenv('GB')
mqtt_broker_in = os.getenv('TRIGGER_MQTT_BROKER')
mqtt_broker_gc = os.getenv('GC_MQTT_BROKER')
# prometheus config
prom_host = os.getenv('PROMETHEUS_HOST')
prom_un = os.getenv('PROMETHEUS_USER')
prom_pass = os.getenv('PROMETHEUS_PASSWORD')
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
    # Initialize MQTT client
    rand_id = "wis2_testing" + str(uuid.uuid4())[:10]
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


def wait_for_messages(sub_client, num_origin_msgs, num_cache_msgs, data_ids=[], interval=0.5, max_wait_time=10, min_wait_time=0):
    """
    Waits for the expected number of origin and cache messages.

    Args:
        sub_client (mqtt.Client): The MQTT client subscribed to the topics.
        num_origin_msgs (int): The expected number of origin messages.
        num_cache_msgs (int): The expected number of cache messages.
        data_ids (list): List of data_ids to filter messages.
        interval (float): The interval to wait between checks (in seconds).
        max_wait_time (int): The maximum time to wait for messages (in seconds).
        min_wait_time (int): The minimum time to wait for messages (in seconds).

    Returns:
        tuple: A tuple containing lists of origin and cache messages.
    """
    elapsed_time = 0
    while elapsed_time < max_wait_time:
        origin_msgs = [m for m in sub_client._userdata['received_messages'] if "origin" in m['topic'] and m['properties']['data_id'] in data_ids]
        cache_msgs = [m for m in sub_client._userdata['received_messages'] if "cache" in m['topic'] and m['properties']['data_id'] in data_ids]
        if len(origin_msgs) >= num_origin_msgs and len(cache_msgs) >= num_cache_msgs and elapsed_time >= min_wait_time:
            print(elapsed_time)
            break
        time.sleep(interval)
        elapsed_time += interval

    return origin_msgs, cache_msgs

@pytest.fixture
def _setup():
    # Setup
    test_centre_int = random.choice(range(datatest_centres[0], datatest_centres[-1] + 1))
    sub_client = setup_mqtt_client(mqtt_broker_out)
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
        result = fetch_prometheus_metrics(metric_name, prometheus_baseurl, username, password, report_by=report_by, centre_id=centre_id)
        metrics[metric_name] = result

    return metrics


def test_mqtt_broker_connectivity():
    print("\nMQTT Broker Connectivity")
    assert mqtt_helpers.check_broker_connectivity(mqtt_broker_gc) is True


@pytest.mark.parametrize("topic", [
    "cache/a/wis2/+/data/core/#",
    "cache/a/wis2/+/metadata/#"
])
def test_mqtt_broker_subscription(topic):
    print("\nGC MQTT Broker Subscription")
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

@pytest.mark.parametrize("run", range(3))
@pytest.mark.usefixtures("_setup")
def test_mqtt_broker_message_flow(run, _setup):
    print("\nWIS2 Notification Message (WNM) Processing")
    # Setup
    _init = _setup
    num_origin_msgs = 1
    sub_client = _init['sub_client']
    wnm_dataset_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid": _init['test_centre_int'],
                "number": num_origin_msgs,
            },
            "wnm": {
                "properties": {
                    "data_id": _init['test_data_id']
                }
            }
        }
    }
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_dataset_config))
    # Wait for messages
    origin_msgs, cache_msgs = wait_for_messages(sub_client, num_origin_msgs, num_origin_msgs)
    sub_client.loop_stop()
    # assert origin and cache messages
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

@pytest.mark.usefixtures("_setup")
def test_cache_false_directive(_setup):
    print("\nCache False Directive")
    num_origin_msgs = 1
    _init = _setup
    # generate some random id's for the messages
    sub_client = _init['sub_client']
    wnm_dataset_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid": _init['test_centre_int'],
                "number": num_origin_msgs,
                "size_min": 128,
                "size_max": 512
            },
            "wnm": {
                "properties": {
                    "cache": False,
                    "data_id": _init['test_data_id'],
                }
            }
        }
    }
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_dataset_config))
    # Wait for messages
    origin_msgs, cache_msgs = wait_for_messages(sub_client, num_origin_msgs, num_origin_msgs)
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
        verified = verify_data(cache_msg, verify_certs=False)
        assert verified is True

@pytest.mark.usefixtures("_setup")
def test_source_download_failure(_setup):
    print("\nSource Download Failure")
    _init = _setup
    num_origin_msgs = 1
    sub_client = _init['sub_client']
    # test_dt = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    # Prepare WNM with invalid data download link
    wnm_dataset_config = {
        "scenario": "wnmtest",
        "configuration": {
            "setup": {
                "centreid": _init['test_centre_int'],
                "number": num_origin_msgs,
                "size_min": 128,
                "size_max": 256
            },
            "wnm": {
                "properties": {
                    "data_id": _init['test_data_id'],
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
    pub_client.pub(topic=_init['test_pub_topic'] , message=json.dumps(wnm_dataset_config))
    del pub_client
    origin_msgs, cache_msgs = wait_for_messages(sub_client, num_origin_msgs, 0, min_wait_time=5)
    sub_client.loop_stop()
    sub_client.disconnect()
    del sub_client

    # Origin Messages
    assert len(origin_msgs) == num_origin_msgs
    # No messages should be published on the cache/a/wis2/# topic
    for origin_msg in origin_msgs:
        # match based on data_id and pubtime
        cache_msg = [m for m in cache_msgs if
                     m['properties']['data_id'] == origin_msg['properties']['data_id'] and m['properties'][
                         'pubtime'] == origin_msg['properties']['pubtime']]
        assert len(cache_msg) == 0


@pytest.mark.usefixtures("_setup")
def test_data_integrity_check_failure(_setup):
    print("\nData Integrity Check Failure")
    _init = _setup
    num_origin_msgs = 1
    sub_client = _init['sub_client']

    # Prepare WNM with invalid data integrity value
    wnm_dataset_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid": _init['test_centre_int'],
                "number": num_origin_msgs,
            },
            "wnm": {
                "properties": {
                    "data_id": _init['test_data_id'],
                    "integrity": {
                        "method": "sha512",
                        "value": "invalid hash"
                    }
                }
            }
        }
    }
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # Publish the message
    pub_result = pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_dataset_config))
    del pub_client
    if not pub_result:
        raise Exception("Failed to publish message")
    # Wait for messages
    origin_msgs, cache_msgs = wait_for_messages(sub_client, num_origin_msgs, 0, min_wait_time=5)
    sub_client.loop_stop()
    sub_client.disconnect()
    del sub_client
    # Origin Messages
    assert len(origin_msgs) == num_origin_msgs
    # No messages should be published on the cache/a/wis2/# topic
    assert len(cache_msgs) == 0


@pytest.mark.usefixtures("_setup")
def test_wnm_deduplication(_setup):
    print("\nWIS2 Notification Message Deduplication")
    _init = _setup
    num_origin_msgs = 5
    sub_client = _init['sub_client']

    # Prepare WNM with duplicate properties
    wnm_dataset_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid": _init['test_centre_int'],
                "number": num_origin_msgs,
                "size_min": 128,
                "size_max": 512
            },
            "wnm": {
                "properties": {
                    "data_id": "deduplication_"+_init['test_data_id'],
                    "pubtime": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
                }
            }
        }
    }
    print(wnm_dataset_config)
    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # Publish the message twice
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_dataset_config))
    pub_client.close()
    del pub_client
    # Wait for messages
    origin_msgs, cache_msgs = wait_for_messages(sub_client, num_origin_msgs, 1)
    sub_client.loop_stop()
    sub_client.disconnect()
    del sub_client
    # Only one message should be published on the cache/a/wis2/# topic
    assert len(origin_msgs) == num_origin_msgs
    assert len(cache_msgs) == 1


@pytest.mark.usefixtures("_setup")
def test_wnm_deduplication_alt_1(_setup):
    print("\nWIS2 Notification Message Deduplication (Alt 1)")
    _init = _setup
    num_origin_msgs = 1
    sub_client = _init['sub_client']
    test_dt = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

    # Prepare WNM with invalid and valid properties
    wnm_invalid_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid": _init['test_centre_int'],
                "number": num_origin_msgs,
                "size_min": 1024,  # 1KB
                "size_max": 1024 * 2  # 2KB
            },
            "wnm": {
                "properties": {
                    "data_id": _init['test_data_id'],
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
    # valid config is the exact same, minus the links property
    wnm_valid_config = deepcopy(wnm_invalid_config)
    wnm_valid_config['configuration']['wnm']['properties'].pop('links')

    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # Publish the invalid message first, then the valid message
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_invalid_config))
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_valid_config))

    # Wait for messages
    origin_msgs, cache_msgs = wait_for_messages(sub_client, num_origin_msgs * 2, 1)

    sub_client.loop_stop()
    sub_client.disconnect()
    del sub_client

    # Assert origin messages
    assert len(origin_msgs) == num_origin_msgs * 2
    # Only one message should be published on the cache/a/wis2/# topic
    assert len(cache_msgs) == 1


@pytest.mark.usefixtures("_setup")
def test_wnm_deduplication_alt_2(_setup):
    print("\nWIS2 Notification Message Deduplication (Alt 2)")
    _init = _setup
    num_origin_msgs = 1
    sub_client = _init['sub_client']
    test_pub_topic = _init['test_pub_topic']
    test_data_id = _init['test_data_id']
    test_dt_1 = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    test_dt_2 = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

    # Prepare WNM with decreasing pubtime
    wnm_config_1 = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid": _init['test_centre_int'],
                "number": num_origin_msgs,
                "size_min": 1024,  # 1KB
                "size_max": 1024 * 2  # 2KB
            },
            "wnm": {
                "properties": {
                    "data_id": test_data_id,
                    "pubtime": test_dt_1,
                }
            }
        }
    }
    # wnm 2 is the same, but with an earlier pubtime
    wnm_config_2 = deepcopy(wnm_config_1)
    wnm_config_2['configuration']['wnm']['properties']['pubtime'] = test_dt_2

    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # Publish the message with later pubtime first, then the earlier pubtime
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_config_1))
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_config_2))

    # Wait for messages
    origin_msgs, cache_msgs = wait_for_messages(sub_client, num_origin_msgs * 2, num_origin_msgs)

    sub_client.loop_stop()
    sub_client.disconnect()
    del sub_client

    # Assert origin messages
    assert len(origin_msgs) == num_origin_msgs * 2
    # Both messages should be published on the origin/a/wis2/# topic but only one on the cache/a/wis2/# topic
    assert len(cache_msgs) == num_origin_msgs


@pytest.mark.usefixtures("_setup")
def test_data_update(_setup):
    print("\nData Update")
    _init = _setup
    num_origin_msgs = 1
    sub_client = _init['sub_client']
    test_pub_topic = _init['test_pub_topic']
    test_data_id = _init['test_data_id']
    test_dt_earlier = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    test_dt_later = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

    # Prepare WNM with earlier pubtime
    wnm_earlier_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid": _init['test_centre_int'],
                "number": num_origin_msgs,
                "size_min": 128,
                "size_max": 512
            },
            "wnm": {
                "properties": {
                    "data_id": test_data_id,
                    "pubtime": test_dt_earlier,
                }
            }
        }
    }

    # Prepare WNM with later pubtime and update link
    wnm_later_config = deepcopy(wnm_earlier_config)
    wnm_later_config['configuration']['wnm']['properties']['pubtime'] = test_dt_later
    wnm_later_config['configuration']['wnm']['links'] = [
        {
            "rel": "update"
        },
    ]

    pub_client = MQTTPubSubClient(mqtt_broker_in)
    # Publish the earlier message first, then the later message
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_earlier_config))
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_later_config))

    # Wait for messages
    origin_msgs, cache_msgs = wait_for_messages(sub_client, num_origin_msgs * 2, num_origin_msgs * 2)

    sub_client.loop_stop()
    sub_client.disconnect()
    del sub_client

    # Assert origin messages
    assert len(origin_msgs) == num_origin_msgs * 2
    assert len(cache_msgs) == num_origin_msgs * 2

    # for each origin message, there should be a corresponding cache message
    for og_wnm in origin_msgs:
        # match based on data_id and pubtime
        cache_msg = [m for m in cache_msgs if
                     m['properties']['data_id'] == og_wnm['properties']['data_id'] and m['properties'][
                         'pubtime'] == og_wnm['properties']['pubtime']]
        assert len(cache_msg) == 1
        cache_msg = cache_msg[0]
        # if the origin wnm has an update link, the corresponding cache wnm should have a canonical link and update link
        if any(l['rel'] == 'update' for l in og_wnm['links']):
            # update and canonical links should be present and equal to origin update link (href)
            assert any(l['rel'] == 'update' for l in cache_msg['links'])
            assert any(l['rel'] == 'canonical' for l in cache_msg['links'])
            # get the update link
            og_update_link = [l['href'] for l in og_wnm['links'] if l['rel'] == 'update'][0]
            # get the cache wnm links
            cache_canonical_link = [l['href'] for l in cache_msg['links'] if l['rel'] == 'canonical'][0]
            cache_update_link = [l['href'] for l in cache_msg['links'] if l['rel'] == 'update'][0]
            assert cache_canonical_link == cache_update_link != og_update_link
        # use pywispubsub to validate the cache messages
        is_valid, errors = validate_message(cache_msg)
        assert is_valid is True
        # verification
        verified = verify_data(cache_msg, verify_certs=False)
        assert verified is True
