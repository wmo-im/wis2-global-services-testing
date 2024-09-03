###############################################################################
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
###############################################################################

import json
import os
import time

from dotenv import load_dotenv
import pytest
from pywis_pubsub.mqtt import MQTTPubSubClient
import requests

if os.path.exists('secrets.env'):
    load_dotenv('secrets.env')

load_dotenv('default.env')

GB = os.environ['GB']
TRIGGER_BROKER = os.environ['TRIGGER_BROKER']
GDC_API = os.environ['GDC_API']
GDC_CENTRE_ID = os.environ['GDC_CENTRE_ID']


TOPICS = [
    'cache/a/wis2/+/metadata/#',
    f'monitor/a/wis2/{GDC_CENTRE_ID}/#'
]

MONITOR_MESSAGES = {}

# fixtures

@pytest.fixture(scope='session')
def gb_client():
    options = {
        'client_id': 'wis2-gdc-test-runner',
        'monitor_messages': {}
    }

    client = MQTTPubSubClient(GB, options)
    yield client

    client.conn.loop_stop()
    client.conn.disconnect()


def subscribe_trigger_client():
    options = {
        'client_id': 'wis2-gdc-test-runner'
    }

    client = MQTTPubSubClient(TRIGGER_BROKER, options)
    client.conn.on_message = _on_message

    return client


# paho-mqtt callbacks

def _on_subscribe(client, userdata, mid, reason_codes, properties):
    client.subscribed_flag = True


def _on_message(client, userdata, message):
    print("TOPIC", message.topic)
    if message.topic.startswith('monitor/a/wis2'):
        report = json.loads(message.payload)

        if report.get('metadata_id') is not None:
            report_metadata_id = report['metadata_id']
        else:
            file_ = report['href'].split('/')[-1]
            report_metadata_id = _get_wcmp2_id_from_filename(file_)

        MONITOR_MESSAGES[report_metadata_id] = report


# helper functions

def _subscribe_gb_client(gb_client_):
    gb_client_.conn.subscribed_flag = False
    gb_client_.conn.on_subscribe = _on_subscribe
    gb_client_.conn.on_message = _on_message
    gb_client_.conn.loop_start()

    for topic in TOPICS:
        _, _ = gb_client_.conn.subscribe(topic)


def _get_wcmp2_id_from_filename(wcmp2_file) -> str:

    id_ = wcmp2_file

    replacers = (
        ('metadata/valid/', ''),
        ('.json', ''),
        ('--', ':'),
        ('badidformat-blank-space', 'badidformat blank-space')
    )

    for replacer in replacers:
        id_ = id_.replace(*replacer)

    return id_


def _publish_wcmp2_trigger_broker_message(wcmp2_file, cache_a_wis2=None) -> None:

    base_url = 'https://raw.githubusercontent.com/wmo-im/wis2-global-services-testing/main/tests/global_discovery_catalogue'

    wcmp2_id = _get_wcmp2_id_from_filename(wcmp2_file)

    message = {
        'scenario': 'metadatatest',
        'configuration': {
            'setup': {
                'centreid': 11,
                'number': 1
            },
            'wnm': {
                'properties': {
                    'metadata_id': wcmp2_id
                },
                'links': [{
                    'href': f'{base_url}/{wcmp2_file}'
                }]
            }
        }
    }

    if cache_a_wis2 is not None:
        message['configuration']['setup']['cache_a_wis2'] = cache_a_wis2

    trigger_client = subscribe_trigger_client()
    trigger_client.pub('config/a/wis2/metadata-pub', json.dumps(message))


def test_global_broker_connection_and_subscription(gb_client):
    print('Testing Global Broker connection and subscription')

    assert gb_client.conn.is_connected

    _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert gb_client.conn.subscribed_flag


def test_notification_and_metadata_processing_success(gb_client):
    print('Testing Notification and metadata processing (success)')

    assert gb_client.conn.is_connected

    _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert gb_client.conn.subscribed_flag

    wcmp2_file = 'metadata/valid/urn--wmo--md--io-wis2dev-11-test--weather.observations.swob-realtime.json'
    wcmp2_id = _get_wcmp2_id_from_filename(wcmp2_file)

    _publish_wcmp2_trigger_broker_message(wcmp2_file)

    time.sleep(5)

    query_url = f'{GDC_API}/items/{wcmp2_id}'

    r = requests.get(query_url)
    assert r.ok

    assert MONITOR_MESSAGES[wcmp2_id]['summary']['PASSED'] == 12


def test_notification_and_metadata_processing_failure_record_not_found(gb_client):
    print('Testing Notification and metadata processing (failure; record not found)')

    assert gb_client.conn.is_connected

    _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert gb_client.conn.subscribed_flag

    wcmp2_file = 'metadata/valid/404.json'

    _publish_wcmp2_trigger_broker_message(wcmp2_file, cache_a_wis2='only')

    print('Test not executed (not cached)')


def test_notification_and_metadata_processing_failure_malformed_json_or_invalid_wcmp2(gb_client):
    print('Testing Notification and metadata processing (failure; malformed JSON or invalid WCMP2)')

    assert gb_client.conn.is_connected

    _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert gb_client.conn.subscribed_flag

    wcmp2_ids = []

    print('Testing malformed JSON')
    for w2p in os.listdir('global_discovery_catalogue/metadata/malformed'):
        _publish_wcmp2_trigger_broker_message(f'metadata/malformed/{w2p}')
        wcmp2_ids.append(_get_wcmp2_id_from_filename(w2p))
        time.sleep(5)

    time.sleep(10)

    for wcmp2_id in wcmp2_ids:
        assert 'message' in MONITOR_MESSAGES[wcmp2_id]

    print('Testing invalid JSON')
    for w2p in os.listdir('global_discovery_catalogue/metadata/invalid'):
        _publish_wcmp2_trigger_broker_message(f'metadata/invalid/{w2p}')
        wcmp2_ids.append(_get_wcmp2_id_from_filename(w2p))
        time.sleep(5)

    for wcmp2_id in wcmp2_ids:
        try:
            assert MONITOR_MESSAGES[wcmp2_id]['summary']['FAILED'] > 0
        except Exception as err:
            assert 'message' in MONITOR_MESSAGES[wcmp2_id]


def test_api_functionality(gb_client):
    print('Testing API functionality')

    wcmp2_ids = []
    for w2p in os.listdir('global_discovery_catalogue/metadata/valid'):
        _publish_wcmp2_trigger_broker_message(f'metadata/valid/{w2p}')
        wcmp2_ids.append(_get_wcmp2_id_from_filename(w2p))

    time.sleep(10)

    for wcmp2_id in wcmp2_ids:
        assert MONITOR_MESSAGES[wcmp2_id]['summary']['PASSED'] == 12

    base_url = GDC_API

    query_url = None

    print('Querying base collection endpoint')
    r = requests.get(base_url).json()

    for link in r['links']:
        if all([link.get('rel') == 'items',
                link.get('type') == 'application/geo+json']):
            query_url = link['href']
            break

    assert query_url is not None

    print('Querying items endpoint')
    r = requests.get(query_url).json()

    assert r['numberMatched'] == 6
    assert r['numberReturned'] == 6

    query_params = {
        'bbox': '-142,42,-53,84'
    }

    print(f'Querying items endpoint with {query_params}')
    r = requests.get(f'{base_url}/items', params=query_params).json()

    assert r['numberMatched'] == 2
    assert r['numberReturned'] == 2
    assert len(r['features']) == 2

    query_params = {
        'datetime': '2000-11-11T12:42:23Z/..'
    }

    print(f'Querying items endpoint with {query_params}')
    r = requests.get(f'{base_url}/items', params=query_params).json()

    assert r['numberMatched'] == 6
    assert r['numberReturned'] == 6
    assert len(r['features']) == 6

    query_params = {
        'q': 'observations'
    }

    print(f'Querying items endpoint with {query_params}')
    r = requests.get(f'{base_url}/items', params=query_params).json()

    assert r['numberMatched'] == 4
    assert r['numberReturned'] == 4
    assert len(r['features']) == 4
