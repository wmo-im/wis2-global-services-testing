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
import paho.mqtt.client as mqtt
import pytest
from pywis_pubsub.mqtt import MQTTPubSubClient
import requests

if os.path.exists('secrets.env'):
    load_dotenv('secrets.env')

load_dotenv('default.env')

TOPIC = 'cache/a/wis2/+/metadata/#'


# fixtures

@pytest.fixture
def gb_client():
    options = {
        'client_id': 'wis2-gdc-test-runner'
    }

    client = MQTTPubSubClient(os.environ['GB'], options)
    return client


def subscribe_trigger_client():
    options = {
        'client_id': 'wis2-gdc-test-runner'
    }

    return MQTTPubSubClient(os.environ['TRIGGER_BROKER'], options)


# paho-mqtt callbacks

def _on_subscribe(client, userdata, mid, reason_codes, properties):
    client.subscribed_flag = True


def _disconnect_gb_client(gb_client_):
    gb_client_.conn.loop_stop()
    gb_client_.conn.disconnect()


# helper functions

def _subscribe_gb_client(gb_client_):
    gb_client_.conn.subscribed_flag = False
    gb_client_.conn.on_subscribe = _on_subscribe
    gb_client_.conn.loop_start()

    return gb_client_.conn.subscribe(TOPIC)


def _publish_wcmp2_trigger_broker_message(wcmp2_file, format_='trigger'):

    base_url = 'https://raw.githubusercontent.com/wmo-im/wis2-global-services-testing/main/tests/global_discovery_catalogue'

    if format_ == 'trigger':
        message = {
            'scenario': 'metadatatest',
            'configuration': {
                'setup': {
                    'cache_a_wis2': 'only',
                    'centreid': 11,
                    'number': 1
                },
                'wnm': {
                    'links': [{
                        'href': f'{base_url}/{wcmp2_file}'
                    }]
                }
            }
        }

    trigger_client = subscribe_trigger_client()
    trigger_client.pub('config/a/wis2/metadata-pub', json.dumps(message))


def test_global_broker_connection_and_subscription(gb_client):
    print('Testing Global Broker connection and subscription')

    assert gb_client.conn.is_connected

    result, _ = _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert result is mqtt.MQTT_ERR_SUCCESS
    assert gb_client.conn.subscribed_flag

    _disconnect_gb_client(gb_client)


def test_notification_and_metadata_processing_success(gb_client):
    print('Testing Notification and metadata processing (success)')

    assert gb_client.conn.is_connected

    result, _ = _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert result is mqtt.MQTT_ERR_SUCCESS
    assert gb_client.conn.subscribed_flag

    _publish_wcmp2_trigger_broker_message('valid/urnwmomdca-eccc-mscweather.observations.swob-realtime.json')

    print("USERDATA", gb_client.userdata)
    print("USERDATA", gb_client.conn._userdata)

    _disconnect_gb_client(gb_client)


def test_api_functionality():
    print('Testing API functionality')
    base_url = os.environ['GDC_API']

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
