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
# sleep factor
sleep_factor = int(os.getenv('SLEEP_FACTOR', 1))
# GB Topics
sub_topics = [
    "origin/a/wis2/#",
    "cache/a/wis2/#",
]


def sleep_w_status(duration):
    """
    Sleeps for the specified duration while printing a status bar to the console.

    Args:
        duration (int): The duration to sleep in seconds.
    """
    print(f"Sleeping for {duration} seconds")
    interval = 0.5  # Update interval for the status bar
    steps = int(duration / interval)

    for i in range(steps + 1):
        time.sleep(interval)
        progress = (i / steps) * 100
        bar_length = 40
        block = int(bar_length * (i / steps))
        status_bar = f"\r[{'#' * block}{'-' * (bar_length - block)}] {progress:.2f}%"
        print(status_bar, end='', flush=True)
    print("\nDone!")


def get_metric_value(metrics, metric_name, centre_id=None, dataserver=None, default=None):
    # Filter metrics by metric_name
    metric_list = metrics.get(metric_name, [])

    # Further filter by centre_id if provided
    if centre_id is not None:
        metric_list = [metric for metric in metric_list if metric['metric'].get('centre_id') == centre_id]

    # Further filter by dataserver if provided
    if dataserver is not None:
        metric_list = [metric for metric in metric_list if metric['metric'].get('dataserver') == dataserver]

    # Return the metric value if found, otherwise return the default value
    if metric_list:
        if len(metric_list) > 1:
            logging.warning(f"Multiple metrics found for {metric_name} with centre_id={centre_id} and dataserver={dataserver}")
        return float(metric_list[0]['value'][1])
    return default

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
        time.sleep(1 * sleep_factor)  # Wait for connection
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
        if connection_info.port in [443, 8883]:
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
    # print summary message
    print(f"Waiting for messages: Origin={num_origin_msgs}, Cache={num_cache_msgs}, Result={num_result_msgs}")
    if sleep_factor != 1:
        print(f"Sleep factor: {sleep_factor}")
        max_wait_time = max_wait_time * sleep_factor
        min_wait_time = min_wait_time * sleep_factor
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
                    print(f"Origin/Cache messages received within {elapsed_time:.2f} seconds.")
                    break
            if num_result_msgs != 0:
                if len(result_msgs) >= num_result_msgs:
                    print(f"{num_result_msgs} Result messages received within {elapsed_time:.2f} seconds.")
                    break

        time.sleep(interval)

    elapsed_time = time.time() - start_time
    if elapsed_time >= max_wait_time:
        print(f"Max wait time of {max_wait_time} seconds reached.")
    if min_wait_time > 0 and elapsed_time < min_wait_time:
        print(f"Min wait time of {min_wait_time} seconds reached.")

    return origin_msgs, cache_msgs, result_msgs


def _setup(test_centre_int:int=None):
    # Setup
    if test_centre_int is None:
        test_centre_int = random.choice(range(datatest_centres[0], datatest_centres[-1] + 1))
    sub_client = setup_mqtt_client(mqtt_broker_recv)
    for sub_topic in sub_topics:
        sub_client.subscribe(sub_topic, qos=1)
        print(f"Subscribed to topic: {sub_topic}")
    test_centre = f"gc_test_centre_{test_centre_int}"
    # format like the actual pub centre ie io-wis2dev-12-test
    test_pub_centre = f"io-wis2dev-{test_centre_int}-test"
    test_pub_topic = f"config/a/wis2/{test_centre}"
    test_data_id = f"{test_centre}_{uuid.uuid4().hex[:16]}"
    # Yield setup data and initial metrics
    setup_dict = {
        "test_centre_int": test_centre_int,
        "sub_client": sub_client,
        "test_centre": test_centre,
        "test_pub_centre": test_pub_centre,
        "test_pub_topic": test_pub_topic,
        "test_data_id": test_data_id,
    }
    return setup_dict


@pytest.fixture(scope="session")
def initial_metrics():
    print("\nFetching initial metrics")
    # Fetch initial metrics before any tests are run
    initial_metrics = get_gc_metrics(prom_host, prom_un, prom_pass)
    return initial_metrics


@pytest.fixture(scope="session")
def metrics_data():
    data = {
    }
    yield data



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
    print(f"Report by: {report_by}")
    metric_job = os.getenv('GC_METRICS_JOB', None)
    print(f"Job: {metric_job}")
    if centre_id is not None:
        centre_id = f'io-wis2dev-{centre_id}-test'
    metrics_to_fetch = [
        "wmo_wis2_gc_downloaded_total",
        "wmo_wis2_gc_dataserver_status_flag",
        "wmo_wis2_gc_downloaded_last_timestamp_seconds",
        "wmo_wis2_gc_dataserver_last_download_timestamp_seconds",
        "wmo_wis2_gc_downloaded_errors_total",
        "wmo_wis2_gc_integrity_failed_total",
        "wmo_wis2_gc_no_cache_total",
        "wmo_wis2_gc_cache_override_total",
        "wmo_wis2_gc_last_metadata_timestamp_seconds"
    ]

    metrics = {}
    for metric_name in metrics_to_fetch:
        labels = []
        if report_by:
            labels.append(f'report_by="{report_by}"')
        if centre_id:
            labels.append(f'centre_id="{centre_id}"')
        if metric_job:
            labels.append(f'job="{metric_job}"')
        query = f'{metric_name}{{{",".join(labels)}}}'
        result = fetch_prometheus_metrics(query, prometheus_baseurl, username, password)
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
    time.sleep(1 * sleep_factor)  # Wait for subscription
    assert result is mqtt.MQTT_ERR_SUCCESS
    assert client.subscribed_flag is True
    client.loop_stop()
    client.disconnect()
    del client


def test_mqtt_broker_message_flow(metrics_data, initial_metrics):
    print("\nWIS2 Notification Message (WNM) Processing")
    # Setup
    _init = _setup(12)
    num_origin_msgs = 1
    sub_client = _init['sub_client']
    wnm_dataset_config = {
        "scenario": "datatest",
        "configuration": {
            "setup": {
                "centreid": _init['test_centre_int'],
                "number": num_origin_msgs,
                "delay": 200,
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
    origin_msg_dataservers = []
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
        dataserver = next((urlparse(link['href']).hostname for link in origin_msg.get('links', []) if link.get('rel') == 'canonical'), None)
        origin_msg_dataservers.append(dataserver)

    metrics_data["assertions"] = metrics_data.get("assertions", [])
    metrics_data["assertions"].append({
        "test_name": "test_mqtt_broker_message_flow",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_downloaded_total",
        "expected_difference": num_origin_msgs,
    })
    # Add assertion for dataserver status flag
    metrics_data["assertions"].append({
        "test_name": "test_mqtt_broker_message_flow",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_status_flag",
        "expected_value": 1,
        "dataservers": origin_msg_dataservers
    })
    metrics_data["assertions"].append({
        "test_name": "test_mqtt_broker_message_flow",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_downloaded_last_timestamp_seconds",
        "expected_comparison": "greater",
        "dataservers": origin_msg_dataservers
    })


def test_cache_false_directive(metrics_data):
    print("\nCache False Directive")
    num_origin_msgs = 1
    _init = _setup(13)
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
    origin_msg_dataservers = []
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
        dataserver = next((urlparse(link['href']).hostname for link in origin_msg.get('links', []) if link.get('rel') == 'canonical'), None)
        origin_msg_dataservers.append(dataserver)
    # metrics assertions
    metrics_data["assertions"] = metrics_data.get("assertions", [])
    metrics_data["assertions"].append({
        "test_name": "test_cache_false_directive",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_no_cache_total",
        "expected_difference": num_origin_msgs,
    })
    metrics_data["assertions"].append({
        "test_name": "test_cache_false_directive",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_downloaded_total",
        "expected_difference": 0,
    })
    metrics_data["assertions"].append({
        "test_name": "test_cache_false_directive",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_status_flag",
        "expected_comparison": "equal",
        "dataservers": origin_msg_dataservers
    })
    metrics_data["assertions"].append({
        "test_name": "test_cache_false_directive",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_last_download_timestamp_seconds",
        "expected_comparison": "equal",
        "dataservers": origin_msg_dataservers
    })


def test_source_download_failure(metrics_data):
    print("\nSource Download Failure")
    _init = _setup(14)
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
    origin_msg_dataservers = []
    for origin_msg in origin_msgs:
        # match based on data_id and pubtime
        cache_msg = [m for m in cache_msgs if
                     m['properties']['data_id'] == origin_msg['properties']['data_id'] and m['properties'][
                         'pubtime'] == origin_msg['properties']['pubtime']]
        assert len(cache_msg) == 0
        dataserver = next(
            (urlparse(link['href']).hostname for link in origin_msg.get('links', []) if link.get('rel') == 'canonical'),
            None)
        origin_msg_dataservers.append(dataserver)
    # metrics assertions

    metrics_data["assertions"] = metrics_data.get("assertions", [])
    metrics_data["assertions"].append({
        "test_name": "test_source_download_failure",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_download_total",
        "expected_difference": 0,
    })
    metrics_data["assertions"].append({
        "test_name": "test_source_download_failure",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_status_flag",
        "expected_value": 0,
        "dataservers": origin_msg_dataservers
    })
    metrics_data["assertions"].append({
        "test_name": "test_source_download_failure",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_last_download_timestamp_seconds",
        "expected_difference": 0,
        "dataservers": origin_msg_dataservers
    })
    metrics_data["assertions"].append({
        "test_name": "test_source_download_failure",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_downloaded_errors_total",
        "expected_difference": num_origin_msgs,
    })

def test_data_integrity_check_failure(metrics_data):
    print("\nData Integrity Check Failure")
    _init = _setup(15)
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

    metrics_data["assertions"] = metrics_data.get("assertions", [])
    metrics_data["assertions"].append({
        "test_name": "test_data_integrity_check_failure",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_download_total",
        "expected_difference": 0,
    })
    metrics_data["assertions"].append({
        "test_name": "test_data_integrity_check_failure",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_status_flag",
        "expected_value": 0,
        # "dataservers": origin_msg_dataservers
    })
    metrics_data["assertions"].append({
        "test_name": "test_data_integrity_check_failure",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_last_download_timestamp_seconds",
        "expected_difference": 0,
        # "dataservers": origin_msg_dataservers
    })
    metrics_data["assertions"].append({
        "test_name": "test_data_integrity_check_failure",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_downloaded_errors_total",
        "expected_difference": num_origin_msgs,
    })
    metrics_data["assertions"].append({
        "test_name": "test_data_integrity_check_failure",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_integrity_failed_total",
        "expected_difference": num_origin_msgs,
    })


def test_wnm_deduplication(metrics_data):
    print("\nWIS2 Notification Message Deduplication")
    _init = _setup(16)
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

    # get origin dataservers
    origin_msg_dataservers = []
    for origin_msg in origin_msgs:
        dataserver = next((urlparse(link['href']).hostname for link in origin_msg.get('links', []) if link.get('rel') == 'canonical'), None)
        origin_msg_dataservers.append(dataserver)
    origin_msg_dataservers = list(set(origin_msg_dataservers))

    metrics_data["assertions"] = metrics_data.get("assertions", [])
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_download_total",
        "expected_difference": 1,
    })
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_status_flag",
        "expected_value": 1,
        "dataservers": origin_msg_dataservers
    })
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_last_download_timestamp_seconds",
        "expected_comparison": "greater",
        "dataservers": origin_msg_dataservers
    })
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_downloaded_errors_total",
        "expected_difference": 0,
    })
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_integrity_failed_total",
        "expected_difference": 0,
    })


def test_wnm_deduplication_alt_1(metrics_data):
    print("\nWIS2 Notification Message Deduplication (Alt 1)")
    _init = _setup(17)
    num_origin_msgs = 1
    sub_client = _init['sub_client']
    msg_data_id = "gc_dedup_alt_1_"+_init['test_data_id']
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
                    "data_id": msg_data_id,
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
                    "data_id": msg_data_id,
                    "pubtime": test_dt
                }
            }
        }
    }

    pub_client = MQTTPubSubClient(mqtt_broker_trigger)
    # Publish the invalid message first, then the valid message
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_invalid_config))
    time.sleep(2 * sleep_factor)
    pub_client.pub(topic=_init['test_pub_topic'], message=json.dumps(wnm_valid_config))

    # Wait for messages
    origin_msgs, cache_msgs, result_msgs = wait_for_messages(sub_client, num_origin_msgs=num_origin_msgs * 2, num_cache_msgs=num_origin_msgs, data_ids=[msg_data_id], max_wait_time=60*2)

    sub_client.loop_stop()
    sub_client.disconnect()
    del sub_client

    # Assert origin messages
    assert len(origin_msgs) == num_origin_msgs * 2
    # Only one message should be published on the cache/a/wis2/# topic
    assert len(cache_msgs) == 1
    # get origin dataservers
    origin_msg_dataservers = []
    for origin_msg in origin_msgs:
        dataserver = next((urlparse(link['href']).hostname for link in origin_msg.get('links', []) if link.get('rel') == 'canonical'), None)
        origin_msg_dataservers.append(dataserver)
    origin_msg_dataservers = list(set(origin_msg_dataservers))
    metrics_data["assertions"] = metrics_data.get("assertions", [])
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication_alt_1",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_download_total",
        "expected_difference": num_origin_msgs,
    })
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication_alt_1",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_status_flag",
        "expected_value": 1,
        "dataservers": [x for x in origin_msg_dataservers if 'example.org' not in x]
    })
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication_alt_1",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_last_download_timestamp_seconds",
        "expected_comparison": "greater",
        "dataservers": [x for x in origin_msg_dataservers if 'example.org' not in x]
    })
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication_alt_1",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_downloaded_errors_total",
        "expected_difference": num_origin_msgs,
    })
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication_alt_1",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_integrity_failed_total",
        "expected_difference": 0,
    })


def test_wnm_deduplication_alt_2(metrics_data):
    print("\nWIS2 Notification Message Deduplication (Alt 2)")
    _init = _setup(18)
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
    time.sleep(2 * sleep_factor)
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
    origin_msg_dataservers = []
    for origin_msg in origin_msgs:
        dataserver = next((urlparse(link['href']).hostname for link in origin_msg.get('links', []) if link.get('rel') == 'canonical'), None)
        origin_msg_dataservers.append(dataserver)
    origin_msg_dataservers = list(set(origin_msg_dataservers))
    metrics_data["assertions"] = metrics_data.get("assertions", [])
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication_alt_2",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_download_total",
        "expected_difference": 1,
    })
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication_alt_2",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_status_flag",
        "expected_value": 1,
        "dataservers": origin_msg_dataservers
    })
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication_alt_2",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_last_download_timestamp_seconds",
        "expected_comparison": "greater",
        "dataservers": origin_msg_dataservers
    })
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication_alt_2",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_downloaded_errors_total",
        "expected_difference": 0,
    })
    metrics_data["assertions"].append({
        "test_name": "test_wnm_deduplication_alt_2",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_integrity_failed_total",
        "expected_difference": 0,
    })

def test_data_update(metrics_data):
    print("\nData Update")
    _init = _setup(19)
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
    time.sleep(10 * sleep_factor)
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
    origin_msg_dataservers = []
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
        dataserver = next((urlparse(link['href']).hostname for link in og_wnm.get('links', []) if
                           link.get('rel') in ['canonical', 'update']), None)
        origin_msg_dataservers.append(dataserver)
    origin_msg_dataservers = list(set(origin_msg_dataservers))
    metrics_data["assertions"] = metrics_data.get("assertions", [])
    metrics_data["assertions"].append({
        "test_name": "test_data_update",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_download_total",
        "expected_difference": num_origin_msgs,
    })
    metrics_data["assertions"].append({
        "test_name": "test_data_update",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_status_flag",
        "expected_value": 1,
        "dataservers": origin_msg_dataservers
    })
    metrics_data["assertions"].append({
        "test_name": "test_data_update",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_dataserver_last_download_timestamp_seconds",
        "expected_comparison": "greater",
        "dataservers": origin_msg_dataservers
    })
    metrics_data["assertions"].append({
        "test_name": "test_data_update",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_downloaded_errors_total",
        "expected_difference": 0,
    })
    metrics_data["assertions"].append({
        "test_name": "test_data_update",
        "centre_id": _init['test_pub_centre'],
        "metric_name": "wmo_wis2_gc_integrity_failed_total",
        "expected_difference": 0,
    })

def test_gc_metrics(metrics_data, initial_metrics):
    print("\nGC Metrics Assertions")
    sleep_w_status(2*60)
    final_metrics = get_gc_metrics(prom_host, prom_un, prom_pass)
    assertion_results = []

    for assertion in metrics_data.get("assertions", []):
        print(f"Checking assertion: {assertion}")
        test_name = assertion.get("test_name")
        centre_id = assertion.get("centre_id")
        metric_name = assertion.get("metric_name")
        expected_difference = assertion.get("expected_difference", None)
        expected_value = assertion.get("expected_value", None)
        expected_comparison = assertion.get("expected_comparison", None)
        dataservers = assertion.get("dataservers", None)

        if dataservers:
            initial_value = get_metric_value(initial_metrics, metric_name, centre_id, dataservers[0], default=0)
            final_value = get_metric_value(final_metrics, metric_name, centre_id, dataservers[0], default=0)
        else:
            initial_value = get_metric_value(initial_metrics, metric_name, centre_id, default=0)
            final_value = get_metric_value(final_metrics, metric_name, centre_id, default=0)

        if expected_difference is not None:
            try:
                assert final_value == initial_value + expected_difference, \
                    f"{test_name}: Expected {metric_name} to increase by {expected_difference} but got {final_value - initial_value}"
            except AssertionError as e:
                assertion_results.append(str(e))

        if expected_value is not None:
            try:
                assert final_value == expected_value, \
                    f"{test_name}: Expected {metric_name} to be {expected_value} but got {final_value}"
            except AssertionError as e:
                assertion_results.append(str(e))

        if expected_comparison == "greater":
            try:
                assert final_value > initial_value, \
                    f"{test_name}: Expected {metric_name} to be greater than {initial_value} but got {final_value}"
            except AssertionError as e:
                assertion_results.append(str(e))

        if expected_comparison == "equal":
            try:
                assert final_value == initial_value, \
                    f"{test_name}: Expected {metric_name} to be equal to {initial_value} but got {final_value}"
            except AssertionError as e:
                assertion_results.append(str(e))

    if assertion_results:
        print("\n".join(assertion_results))
        raise AssertionError("\n".join(assertion_results))