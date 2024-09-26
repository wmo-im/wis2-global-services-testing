import json
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
ab_centres = [1001, 1010]

# Connection strings for the development global broker and message generator
# Access the environment variables
load_dotenv("./global-cache.env")
load_dotenv("../secrets.env")
load_dotenv("../default.env")
mqtt_broker_recv = os.getenv('GB')
mqtt_broker_trigger = os.getenv('TRIGGER_BROKER')
mqtt_broker_gc = os.getenv('TEST_GC_MQTT_BROKER')
# prometheus config
prom_host = os.getenv('PROMETHEUS_HOST')
prom_un = os.getenv('PROMETHEUS_USER')
prom_pass = os.getenv('PROMETHEUS_PASSWORD')
# GB Topics
sub_topics = [
    "origin/a/wis2/#",
    "cache/a/wis2/#",
]


def check_broker_connectivity(connection_string: str):
    """
    Check if the broker is reachable
    :param connection_string:
    :return:
    """
    # return True if connection is successful, False otherwise
    is_connected = False
    try:
        client = setup_mqtt_client(connection_string, on_log=True, loop_start=True)
        if client.is_connected():
            is_connected = True
        client.loop_stop()
        client.disconnect()
    except Exception as e:
        print(f"Connection error: {e}")
    return is_connected


def parse_timestamp(data_string):
    formats = ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ']
    parsed_time = None
    for fmt in formats:
        try:
            parsed_time = datetime.strptime(data_string, fmt)
            parsed_time = parsed_time.replace(tzinfo=timezone.utc)  # Ensure timezone awareness
            break
        except ValueError:
            continue

    if parsed_time is None:
        raise ValueError(f"time data {data_string!r} does not match any known format")

    return parsed_time


def flag_on_connect(client, userdata, flags, rc, properties=None):
    # print("Connected with result code " + str(rc))
    if rc == 0:
        client.connected_flag = True
    else:
        client.connected_flag = False


def flag_on_disconnect(client, userdata, reason_code, properties=None):
    if reason_code == 0:
        logging.info("Clean disconnection")
    else:
        logging.error(f"Disconnect error with reason code {reason_code}")


def flag_on_subscribe(client, userdata, mid, reason_codes, properties=None):
    print("Subscribed with mid " + str(mid) + " and QoS " + str(reason_codes[0]))
    client.subscribed_flag = True


def flag_on_message(client, userdata, msg):
    # print(f"Received message: {msg.topic} {msg.payload}")
    try:
        msg_json = json.loads(msg.payload.decode())
    except:
        msg_json = {'payload': msg.payload.decode()}
    msg_json['topic'] = msg.topic
    msg_json['received_time'] = time.time()
    client._userdata['received_messages'].append(msg_json)

    # Record timestamps
    if "origin" in msg.topic:
        if 'origin_start_time' not in client._userdata:
            client._userdata['origin_start_time'] = time.time()
        client._userdata['origin_end_time'] = time.time()
    elif "cache" in msg.topic:
        if 'cache_start_time' not in client._userdata:
            client._userdata['cache_start_time'] = time.time()
        client._userdata['cache_end_time'] = time.time()


def setup_mqtt_client(connection_info: str, on_log=False, loop_start=True):
    """
    Set up an MQTT client for testing.
    Args:
        on_log: use on_log callback to print logs
        connection_info: connection string for the MQTT broker.
        loop_start: use the async loop to connect

    Returns: paho MQTT client

    """
    # Initialize MQTT client
    rand_id = "gc_test_client_" + str(uuid.uuid4())[:10]
    client = mqtt.Client(client_id=rand_id, protocol=mqtt.MQTTv5, userdata={'received_messages': []})
    client.on_connect = flag_on_connect
    client.on_subscribe = flag_on_subscribe
    client.on_disconnect = flag_on_disconnect
    client.on_message = flag_on_message
    if on_log:
        client.on_log = lambda client, userdata, level, buf: print(f"Log: {buf}")
    # Parse connection info
    connection_info = urlparse(connection_info)
    client.username_pw_set(connection_info.username, connection_info.password)

    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = 300  # seconds
    if connection_info.port in [443, 8883]:
        tls_settings = {'tls_version': 2, 'cert_reqs': mqtt.ssl.CERT_NONE}
        client.tls_set(**tls_settings)

    try:
        client.connect(host=connection_info.hostname, port=connection_info.port, properties=properties)
        if loop_start:
            client.loop_start()
        time.sleep(1)  # Wait for connection
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
        # tls configuration
        print(f"  TLS: {tls_settings}")
        raise

    return client


def wait_for_messages(sub_client, num_origin_msgs=0, num_cache_msgs=0, num_result_msgs=0, data_ids=[], interval=0.5, max_wait_time=10, min_wait_time=0):
    """
    Waits for the expected number of origin and cache messages.

    Args:
        sub_client (mqtt.Client): The MQTT client subscribed to the topics.
        num_origin_msgs (int): The expected number of origin messages.
        num_cache_msgs (int): The expected number of cache messages.
        num_result_msgs (int): The expected number of result messages.
        data_ids (list): List of data_ids to filter messages.
        interval (float): The interval to wait between checks (in seconds).
        max_wait_time (int): The maximum time to wait for messages (in seconds).
        min_wait_time (int): The minimum time to wait for messages (in seconds).

    Returns:
        tuple: A tuple containing lists of origin and cache messages, and a string indicating the reason for the break.
    """
    start_time = time.time()

    while time.time() - start_time < max_wait_time:
        if data_ids:
            origin_msgs = [m for m in sub_client._userdata['received_messages'] if "origin" in m['topic'] and m['properties']['data_id'] in data_ids]
            cache_msgs = [m for m in sub_client._userdata['received_messages'] if "cache" in m['topic'] and m['properties']['data_id'] in data_ids]
            result_msgs = [m for m in sub_client._userdata['received_messages'] if "result" in m['topic'] and m['properties']['data_id'] in data_ids]
        else:
            origin_msgs = [m for m in sub_client._userdata['received_messages'] if "origin" in m['topic']]
            cache_msgs = [m for m in sub_client._userdata['received_messages'] if "cache" in m['topic']]
            result_msgs = [m for m in sub_client._userdata['received_messages'] if "result" in m['topic']]

        elapsed_time = time.time() - start_time
        if elapsed_time >= min_wait_time:
            if num_cache_msgs != 0 and num_origin_msgs != 0:
                if len(origin_msgs) >= num_origin_msgs and len(cache_msgs) >= num_cache_msgs:
                    print(f"Origin/Cache messages received within {elapsed_time} seconds.")
                    break
            if num_result_msgs != 0:
                if len(result_msgs) >= num_result_msgs:
                    print(f"{num_result_msgs} Result messages received within {elapsed_time} seconds.")
                    break

        time.sleep(interval)

    elapsed_time = time.time() - start_time
    if elapsed_time >= max_wait_time:
        print(f"Max wait time of {max_wait_time} seconds reached.")
    elif elapsed_time < min_wait_time:
        print(f"Min wait time of {min_wait_time} seconds reached.")

    return origin_msgs, cache_msgs, result_msgs


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


def test_mqtt_broker_connectivity():
    print("\nMQTT Broker Connectivity")
    assert check_broker_connectivity(mqtt_broker_gc) is True


@pytest.mark.parametrize("topic", [
    "cache/a/wis2/+/data/core/#",
    "cache/a/wis2/+/metadata/#"
])
def test_mqtt_broker_subscription(topic):
    print("\nGC MQTT Broker Subscription")
    print(f"Subscribing to topic: {topic}")
    # Use setup_mqtt_client function to initialize the client
    client = setup_mqtt_client(mqtt_broker_gc, on_log=True, loop_start=True)
    client.subscribed_flag = False
    result, mid = client.subscribe(topic)
    time.sleep(1)  # Wait for subscription
    assert result is mqtt.MQTT_ERR_SUCCESS
    assert client.subscribed_flag is True
    client.loop_stop()
    client.disconnect()
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
                # "cache_a_wis2": "mix",
            },
            "wnm": {
                "properties": {
                    "data_id": _init['test_data_id']
                }
            }
        }
    }
    pub_client = MQTTPubSubClient(mqtt_broker_trigger)
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_dataset_config))
    # Wait for messages
    origin_msgs, cache_msgs, result_msgs = wait_for_messages(sub_client, num_origin_msgs, num_origin_msgs,
                                                data_ids=[_init['test_data_id']], max_wait_time=60*5)
    sub_client.loop_stop()
    # assert origin and cache messages
    assert len(origin_msgs) >= num_origin_msgs
    assert len(cache_msgs) >= num_origin_msgs

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
    pub_client = MQTTPubSubClient(mqtt_broker_trigger)
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_dataset_config))
    # Wait for messages
    origin_msgs, cache_msgs, result_msgs = wait_for_messages(sub_client, num_origin_msgs, num_origin_msgs,
                                                data_ids=[_init['test_data_id']])
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
    pub_client = MQTTPubSubClient(mqtt_broker_trigger)
    # Publish the message
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_dataset_config))
    del pub_client
    origin_msgs, cache_msgs, result_msgs = wait_for_messages(sub_client, num_origin_msgs, 0, data_ids=[_init['test_data_id']],
                                                min_wait_time=5)
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
    pub_client = MQTTPubSubClient(mqtt_broker_trigger)
    # Publish the message
    pub_result = pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_dataset_config))
    del pub_client
    if not pub_result:
        raise Exception("Failed to publish message")
    # Wait for messages
    origin_msgs, cache_msgs, result_msgs = wait_for_messages(sub_client, num_origin_msgs, 0, data_ids=[_init['test_data_id']],
                                                min_wait_time=5)
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
                    "data_id": "deduplication_" + _init['test_data_id'],
                    "pubtime": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
                }
            }
        }
    }
    print(wnm_dataset_config)
    pub_client = MQTTPubSubClient(mqtt_broker_trigger)
    # Publish the message twice
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_dataset_config))
    pub_client.close()
    del pub_client
    # Wait for messages
    origin_msgs, cache_msgs, result_msgs = wait_for_messages(sub_client, num_origin_msgs, 1, max_wait_time=120, min_wait_time=60)
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
                    "pubtime": test_dt,
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

    wnm_valid_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid": _init['test_centre_int'],
                "number": num_origin_msgs,
                "size_min": 128,
                "size_max": 512,
                "embed_data": False
            },
            "wnm": {
                "properties": {
                    "data_id": _init['test_data_id'],
                    "pubtime": test_dt
                }
            }
        }
    }

    pub_client = MQTTPubSubClient(mqtt_broker_trigger)
    # Publish the invalid message first, then the valid message
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_invalid_config))
    time.sleep(5)
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_valid_config))

    # Wait for messages
    origin_msgs, cache_msgs, result_msgs = wait_for_messages(sub_client, num_origin_msgs * 2, num_cache_msgs=1, data_ids=[_init['test_data_id']], max_wait_time=60*2)

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

    pub_client = MQTTPubSubClient(mqtt_broker_trigger)
    # Publish the message with later pubtime first, then the earlier pubtime
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_config_1))
    time.sleep(2)
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_config_2))

    # Wait for messages
    origin_msgs, cache_msgs, result_msgs = wait_for_messages(sub_client, num_origin_msgs * 2, num_origin_msgs, data_ids=[test_data_id], max_wait_time=60)

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
                    "data_id": _init['test_data_id'],
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

    pub_client = MQTTPubSubClient(mqtt_broker_trigger)
    # Publish the earlier message first, then the later message
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_earlier_config))
    time.sleep(10)
    pub_client.pub(topic=test_pub_topic, message=json.dumps(wnm_later_config))

    # Wait for messages
    origin_msgs, cache_msgs, result_msgs = wait_for_messages(sub_client, num_origin_msgs * 2, num_origin_msgs * 2,
                                                data_ids=[_init['test_data_id']], max_wait_time=60*2)

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
            # update link should be present and equal to origin update link (href)
            assert any(l['rel'] == 'update' for l in cache_msg['links'])
            # get the update link
            og_update_link = [l['href'] for l in og_wnm['links'] if l['rel'] == 'update'][0]
            # get the cache wnm links
            cache_update_link = [l['href'] for l in cache_msg['links'] if l['rel'] == 'update'][0]
            assert cache_update_link != og_update_link
            cache_canonical_link = [l['href'] for l in cache_msg['links'] if l['rel'] == 'canonical']
            if cache_canonical_link:
                assert cache_canonical_link[0] != og_update_link
                assert cache_canonical_link[0] == cache_update_link
        # use pywispubsub to validate the cache messages
        is_valid, errors = validate_message(cache_msg)
        assert is_valid is True
        # verification
        verified = verify_data(cache_msg, verify_certs=False)
        assert verified is True


def test_wnm_processing_rate(_setup):
    print("\nWIS2 Notification Message Processing Rate")
    _init = _setup
    num_msgs = 2000
    sub_client = _init['sub_client']
    test_pub_topic = _init['test_pub_topic']
    num_msgs_per_centre = num_msgs // (datatest_centres[-1] - datatest_centres[0] + 1)
    num_msgs = num_msgs_per_centre * (datatest_centres[-1] - datatest_centres[0] + 1)
    print(f"Number of messages: {num_msgs}")
    print(f"Number of messages per centre: {num_msgs_per_centre}")

    # Initialize the trigger client
    trigger_client = setup_mqtt_client(mqtt_broker_trigger)
    for centreid in range(datatest_centres[0], datatest_centres[1] + 1):
        wnm_dataset_config = {
            "scenario": "datatest",
            "configuration": {
                "setup": {
                    "centreid_min": centreid,
                    "centreid_max": centreid,
                    "number": num_msgs_per_centre,
                    "size_min": (1000 * 85),
                    "size_max": (1000 * 90),
                    "delay": 0
                }}}
        trigger_client.publish(topic="config/a/wis2/gc_performance_test", payload=json.dumps(wnm_dataset_config), qos=1)
    trigger_client.loop_stop()
    trigger_client.disconnect()

    # Wait for messages
    origin_msgs, cache_msgs, result_msgs = wait_for_messages(sub_client, num_msgs, num_msgs, max_wait_time=60*10)
    msg_data = sub_client._userdata
    sub_client.loop_stop()
    sub_client.disconnect()
    # Assert origin and cache messages
    assert len(origin_msgs) >= num_msgs
    assert len(cache_msgs) >= num_msgs

    # Calculate and print processing metrics
    origin_start_time = msg_data.get('origin_start_time')
    cache_end_time = msg_data.get('cache_end_time')
    if origin_start_time and cache_end_time:
        total_processing_time = cache_end_time - origin_start_time
        print(f"Total processing time from first 'origin' to last 'cache': {total_processing_time:.2f} seconds")
        # print total cache and origin messages
        print(f"Total Origin Messages: {len(origin_msgs)}")
        print(f"Total Cache Messages: {len(cache_msgs)}")

    processing_times = [
        cache_msg['received_time'] - origin_msg['received_time']
        for origin_msg in origin_msgs
        for cache_msg in cache_msgs
        if cache_msg['properties']['data_id'] == origin_msg['properties']['data_id'] and cache_msg['properties'][
            'pubtime'] == origin_msg['properties']['pubtime']
    ]

    if processing_times:
        avg_processing_time = sum(processing_times) / len(processing_times)
        print(f"Average processing time per message: {avg_processing_time:.2f} seconds")

    if origin_start_time and cache_end_time:
        throughput = len(cache_msgs) / total_processing_time
        print(f"Throughput: {throughput:.2f} messages per second")
        assert throughput >= 5, "Throughput is less than 5 messages per second"

    cache_start_time = msg_data.get('cache_start_time')
    if cache_start_time and cache_end_time:
        cache_processing_time = cache_end_time - cache_start_time
        print(f"Cache processing time excluding initial lag: {cache_processing_time:.2f} seconds")
    # calculate the average cache message size
    # msg['links']['canonical']['length']
    cache_msg_sizes = [l['length'] for m in cache_msgs for l in m['links'] if l['rel'] == 'canonical']
    avg_cache_msg_size = sum(cache_msg_sizes) / len(cache_msg_sizes)
    print(f"Average cache message size: {avg_cache_msg_size:.2f} bytes")


# @pytest.mark.parametrize("ab_centreid", range(ab_centres[0], ab_centres[0] + 1))
@pytest.mark.usefixtures("_setup")
# def test_concurrent_client_downloads(ab_centreid, _setup):
def test_concurrent_client_downloads(_setup):
    print("\nConcurrent client downloads")
    _init = _setup
    num_origin_msgs = 1
    sub_client = _init['sub_client']
    concurrency_benchmark = 1000
    # Prepare and publish a normal WNM message
    wnm_dataset_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid": _init['test_centre_int'],
                "number": num_origin_msgs,
                # "size_min": 1000 * 1000 * 200,  # 200MB
                # "size_max": 1000 * 1000 * 201,  # 201MB
                "size_min": 1000 * 1000 * 20,  # 20MB
                "size_max": 1000 * 1000 * 21,  # 21MB
                # "size_min": 1000 * 100,
                # "size_max": 1000 * 101,
            },
            "wnm": {
                "properties": {
                    "data_id": _init['test_data_id'],
                    "cache": True  # Ensure caching for large files
                }
            }
        }
    }

    pub_client = setup_mqtt_client(mqtt_broker_trigger)
    pub_result_1 = pub_client.publish(topic=_init['test_pub_topic'], payload=json.dumps(wnm_dataset_config))
    print(f"Published large file with result: {pub_result_1}")
    # Wait for messages
    origin_msgs, cache_msgs, result_msgs = wait_for_messages(sub_client, num_origin_msgs, num_origin_msgs, max_wait_time=60*5,
                                                data_ids=[_init['test_data_id']])

    # Assert origin and cache messages
    assert len(origin_msgs) == num_origin_msgs
    assert len(cache_msgs) == num_origin_msgs, "Cache messages not received..."

    # Extract the canonical link from the cached messages
    canonical_link = None
    for cache_msg in cache_msgs:
        for link in cache_msg['links']:
            if link['rel'] == 'canonical':
                canonical_link = link['href']
                break
        if canonical_link:
            break

    assert canonical_link is not None, "Canonical link not found in cached messages"
    # Prepare and publish an 'ab' scenario config message using the canonical link
    # number of ab centres
    num_ab_centres = ab_centres[-1] - ab_centres[0] + 1
    ab_scenario_config = {
        "scenario": "ab",
        "configuration": {
            "setup": {
                "centreid_min": ab_centres[0],
                "centreid_max": ab_centres[-1],
                "concurrent": concurrency_benchmark//num_ab_centres,
                "number": concurrency_benchmark*1.5//num_ab_centres,
                "url": canonical_link,
                "action": "start"
            }
        }
    }

    # Subscribe to the result topic
    result_client = setup_mqtt_client(mqtt_broker_trigger)
    result_client.subscribe("result/a/wis2/+/ab", qos=1)

    pub_ab_result = pub_client.publish(topic="config/a/wis2/gcabtest", payload=json.dumps(ab_scenario_config))
    if not pub_ab_result:
        raise Exception("Failed to publish message")
    print(f"Published ApacheBench scenario with result: {pub_ab_result}")

    origin_msgs, cache_msgs, result_msgs = wait_for_messages(result_client, num_result_msgs=num_ab_centres*2, max_wait_time=60*15)
    # collect msgs from result client
    ab_result_msgs = [m for m in result_msgs if 'payload' in m.keys() and 'ApacheBench' in m['payload']]

    # Assert result messages
    assert len(ab_result_msgs) > 0, "No ab result messages received"

    # Perform additional assertions or evaluations on the result messages if needed
    print("\nCollecting and parsing ApacheBench results:\n")
    for r in ab_result_msgs:
        # parse the ab result
        ab_result = ab.parse_ab_output(r['payload'])
        # assert no failed requests
        assert int(ab_result['failed_requests']) == 0
        # log the result
        print(json.dumps(ab_result, indent=4))
