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
GDC_BROKER = os.environ['GDC_BROKER']
GDC_CENTRE_ID = os.environ['GDC_CENTRE_ID']


TOPICS = [
    'cache/a/wis2/+/metadata/#',
    f'monitor/a/wis2/{GDC_CENTRE_ID}/#'
]


# fixtures

@pytest.fixture
def gb_client():
    options = {
        'client_id': 'wis2-gdc-test-runner',
        'monitor_messages': []
    }

    client = MQTTPubSubClient(GB, options)
    yield client


@pytest.fixture
def gdc_broker():
    options = {
        'client_id': 'wis2-gdc-test-runner'
    }

    client = MQTTPubSubClient(GDC_BROKER, options)
    yield client


def subscribe_trigger_client():
    options = {
        'client_id': 'wis2-gdc-test-runner'
    }

    return MQTTPubSubClient(TRIGGER_BROKER, options)


# paho-mqtt callbacks

def _on_subscribe(client, userdata, mid, reason_codes, properties):
    client.subscribed_flag = True


def _on_message(client, userdata, message):
    client._userdata['monitor_messages'].append(message.payload)
    if message.topic.startswith('monitor/a/wis2'):
        client._userdata['monitor_messages'].append(message.payload)


def _disconnect_gb_client(gb_client_):
    gb_client_.conn.loop_stop()
    gb_client_.conn.disconnect()


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
        ('valid/', ''),
        ('.json', ''),
        ('--', ':')
    )

    for replacer in replacers:
        id_ = id_.replace(*replacer)

    return id_


def _publish_wcmp2_trigger_broker_message(wcmp2_file, format_='trigger') -> str:

    base_url = 'https://raw.githubusercontent.com/wmo-im/wis2-global-services-testing/gdc-tests-update/tests/global_discovery_catalogue'

    wcmp2_id = _get_wcmp2_id_from_filename(wcmp2_file)

    if format_ == 'trigger':
        message = {
            'scenario': 'metadatatest',
            'configuration': {
                'setup': {
                    # 'cache_a_wis2': 'only',
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

    trigger_client = subscribe_trigger_client()
    trigger_client.pub('config/a/wis2/metadata-pub', json.dumps(message), qos=0)


def test_global_broker_connection_and_subscription(gb_client, gdc_broker):
    print('Testing Global Broker connection and subscription')

    assert gb_client.conn.is_connected

    _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert gb_client.conn.subscribed_flag

    _disconnect_gb_client(gb_client)


def test_notification_and_metadata_processing_success(gb_client):
    print('Testing Notification and metadata processing (success)')

    assert gb_client.conn.is_connected

    _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert gb_client.conn.subscribed_flag

    wcmp2_file = 'valid/urn--wmo--md--io-wis2dev-11-test--weather.observations.swob-realtime.json'
    wcmp2_id = _get_wcmp2_id_from_filename(wcmp2_file)

    _publish_wcmp2_trigger_broker_message(wcmp2_file)

    time.sleep(5)

    query_url = f'{GDC_API}/items/{wcmp2_id}'

    r = requests.get(query_url)
    assert r.ok

    for m in gb_client.userdata['monitor_messages']:
        print(m)

    _disconnect_gb_client(gb_client)


def itest_api_functionality():
    print('Testing API functionality')

    for w2p in os.listdir('global_discovery_catalogue/valid'):
        _publish_wcmp2_trigger_broker_message(f'valid/{w2p}')

    time.sleep(10)
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
