import argparse
import os
import sys
from dotenv import load_dotenv
import json
from .test_global_cache_functional import _setup, wait_for_messages, setup_mqtt_client
# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared_utils import mqtt_helpers, ab, prom_metrics

ab_centres = [1001, 1010]
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

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Global Cache Functional Tests')
parser.add_argument('--sleep-factor', type=int, default=1, help='Sleep factor for the tests')
args = parser.parse_args()

# sleep factor
sleep_factor = args.sleep_factor
# GB Topics
sub_topics = [
    "origin/a/wis2/#",
    "cache/a/wis2/#",
]


def test_wnm_processing_rate():
    print("\nWIS2 Notification Message Processing Rate")
    _init = _setup()
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
                    "delay": 100
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
# def test_concurrent_client_downloads(ab_centreid):
def test_concurrent_client_downloads():
    print("\nConcurrent client downloads")
    _init = _setup()
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
                "size_min": 1000 * 1000 * 2,  # 2MB
                "size_max": 1000 * 1000 * 2,
            },
            "wnm": {
                "properties": {
                    "data_id": _init['test_data_id'],
                    "cache": True  # Ensure caching
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
