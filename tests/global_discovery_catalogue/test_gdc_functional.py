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

import io
import json
import os
import sys
import time
import zipfile

from dotenv import load_dotenv
import pytest
from pywis_pubsub.mqtt import MQTTPubSubClient
import requests

sys.path.append('.')

from shared_utils.prom_metrics import fetch_prometheus_metrics

if os.path.exists('secrets.env'):
    load_dotenv('secrets.env')

load_dotenv('default.env')

GB = os.environ['GB']
GB_CENTRE_ID = os.environ['GB_CENTRE_ID']
TRIGGER_BROKER = os.environ['TRIGGER_BROKER']
GDC_API = os.environ['GDC_API']
GDC_CENTRE_ID = os.environ['GDC_CENTRE_ID']
PROMETHEUS_HOST = os.getenv('PROMETHEUS_HOST')
PROMETHEUS_USER = os.getenv('PROMETHEUS_USER')
PROMETHEUS_PASSWORD = os.getenv('PROMETHEUS_PASSWORD')

MONITOR_MESSAGES = {}
CACHE_MESSAGES = []

TOPICS = [
    'cache/a/wis2/+/metadata/#',
    f'monitor/a/wis2/{GDC_CENTRE_ID}/#'
]

# fixtures


@pytest.fixture(scope='session')
def gb_client():
    options = {
        'client_id': 'wis2-gdc-test-runner'
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
    global MONITOR_MESSAGES
    global CACHE_MESSAGES
    if message.topic.startswith('monitor/a/wis2'):
        report_metadata_id = ""
        report = json.loads(message.payload)

        if report.get('metadata_id') is not None:
            report_metadata_id = report['metadata_id']
        else:
            href = report.get('href')
            if href is None:
                report_metadata_id = 'no-metadata_id'
            else:
                file_ = report['href'].split('/')[-1]
                report_metadata_id = _get_wcmp2_id_from_filename(file_)
        if report_metadata_id != "":
            MONITOR_MESSAGES[report_metadata_id] = report
    else:
        if message.topic.startswith('cache/a/wis2'):
            cache_msg_id = ""
            if "metadata" in message.topic:
                cache_msg = json.loads(message.payload)
                if cache_msg.get('id') is not None:
                    cache_msg_id = cache_msg['id']
                    CACHE_MESSAGES.update(cache_msg_id)


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


def _publish_wcmp2_trigger_broker_message(wcmp2_file, cache_a_wis2=None, link_rel='canonical',
                                          metadata_id=True) -> None:

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

    if link_rel == 'deletion':
        message['configuration']['wnm']['links'][0]['rel'] = 'deletion'

    if cache_a_wis2 is not None:
        message['configuration']['setup']['cache_a_wis2'] = cache_a_wis2

    if not metadata_id:
        message['configuration']['wnm']['properties']['metadata_id'] = metadata_id

    trigger_client = subscribe_trigger_client()
    trigger_client.pub('config/a/wis2/metadata-pub', json.dumps(message))


def _get_metadata_archive_zipfile_href():

    metadata_archive_zipfile_href = None

    r = requests.get(GDC_API).json()

    for link in r['links']:
        if link.get('rel') == 'archives' and link.get('type') == 'application/zip':
            metadata_archive_zipfile_href = link['href']
            break

    return metadata_archive_zipfile_href


def test_global_broker_connection_and_subscription(gb_client):
    print('Testing Global Broker connection and subscription')

    assert gb_client.conn.is_connected

    _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert gb_client.conn.subscribed_flag

    result = fetch_prometheus_metrics('wmo_wis2_gdc_connected_flag', PROMETHEUS_HOST,
                                      PROMETHEUS_USER, PROMETHEUS_PASSWORD, report_by=GDC_CENTRE_ID,
                                      centre_id=GB_CENTRE_ID)

    assert result[0]['value'][1] == '1'


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

    assert wcmp2_id in CACHE_MESSAGES

    if wcmp2_id in MONITOR_MESSAGES.keys():
        assert MONITOR_MESSAGES[wcmp2_id]['summary']['PASSED'] == 12
    else:
        print(f'{wcmp2_id} not in MONITOR_MESSAGES.keys(): {MONITOR_MESSAGES.keys()}')


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

    time.sleep(10)

    for wcmp2_id in wcmp2_ids:
        assert wcmp2_id in CACHE_MESSAGES
        try:
            assert MONITOR_MESSAGES[wcmp2_id]['summary']['FAILED'] > 0
        except Exception:
            assert 'message' in MONITOR_MESSAGES[wcmp2_id]


def test_metadata_ingest_centre_id_mismatch(gb_client):
    print('Testing Metadata ingest centre-id mismatch')

    assert gb_client.conn.is_connected

    _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert gb_client.conn.subscribed_flag

    print('Testing centre-id mismatch')
    wnm = 'urn--wmo--md--io-wis2dev-11-test--centreid-mismatch.json'
    wcmp2_id = _get_wcmp2_id_from_filename(wnm)

    _publish_wcmp2_trigger_broker_message(f'metadata/invalid/{wnm}')  # noqa
    time.sleep(5)

    assert wcmp2_id in CACHE_MESSAGES

    assert 'message' in MONITOR_MESSAGES[wcmp2_id]


def test_notification_and_metadata_processing_record_deletion(gb_client):
    global CACHE_MESSAGES
    print('Testing Notification and metadata processing (record deletion)')

    assert gb_client.conn.is_connected

    _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert gb_client.conn.subscribed_flag

    wnm = 'urn--wmo--md--io-wis2dev-11-test--data.core.weather.prediction.forecast.shortrange.probabilistic.global.json'
    wcmp2_id = _get_wcmp2_id_from_filename(wnm)

    _publish_wcmp2_trigger_broker_message(f'metadata/valid/{wnm}')  # noqa
    time.sleep(5)

    assert wcmp2_id in CACHE_MESSAGES

    query_url = f'{GDC_API}/items/{wcmp2_id}'

    r = requests.get(query_url)
    assert r.ok

    if wcmp2_id in CACHE_MESSAGES:
        CACHE_MESSAGES.remove(wcmp2_id)

    _publish_wcmp2_trigger_broker_message(f'metadata/valid/{wnm}', link_rel='deletion')  # noqa
    time.sleep(10)

    assert wcmp2_id in CACHE_MESSAGES

    r = requests.get(query_url)
    assert not r.ok

    assert 'message' in MONITOR_MESSAGES[wcmp2_id]


def test_notification_and_metadata_processing_failure_record_deletion_message_does_not_contain_properties_metadata_id(gb_client):  # noqa
    print('Testing Notification and metadata processing (failure; record deletion message does not contain properties.metadata_id)')  # noqa

    assert gb_client.conn.is_connected

    _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert gb_client.conn.subscribed_flag

    wnm = 'urn--wmo--md--io-wis2dev-11-test--data.core.weather.prediction.forecast.shortrange.probabilistic.global.json'

    _publish_wcmp2_trigger_broker_message(f'metadata/valid/{wnm}', link_rel='deletion', metadata_id=False)  # noqa
    time.sleep(5)

    # CACHE_MESSAGES.update uses id from payload so it should work
    wcmp2_id = "urn:wmo:md:io-wis2dev-11-test:data.core.weather.prediction.forecast.shortrange.probabilistic.global"
    assert wcmp2_id in CACHE_MESSAGES

    assert 'message' in MONITOR_MESSAGES['no-metadata_id']


def test_wcmp2_metadata_archive_zipfile_publication(gb_client):
    print('Testing WCMP2 metadata archive zipfile publication')

    metadata_archive_zipfile_href = _get_metadata_archive_zipfile_href()

    assert metadata_archive_zipfile_href is not None

    r = requests.get(metadata_archive_zipfile_href)

    assert r.headers['Content-Type'] == 'application/zip'

    content = io.BytesIO(r.content)
    with zipfile.ZipFile(content) as z:
        for name in z.namelist():
            with z.open(name) as zfh:
                record = json.load(zfh)
                assert 'http://wis.wmo.int/spec/wcmp/2/conf/core' in record['conformsTo']


def test_wcmp2_cold_start_initialization_from_metadata_archive_zipfile(gb_client):
    print('Testing WCMP2 cold start initialization from metadata archive zipfile')

    pass


def test_api_functionality(gb_client):
    print('Testing API functionality')

    assert gb_client.conn.is_connected

    _subscribe_gb_client(gb_client)

    time.sleep(1)

    assert gb_client.conn.subscribed_flag

    wcmp2_ids = []
    for w2p in os.listdir('global_discovery_catalogue/metadata/valid'):
        _publish_wcmp2_trigger_broker_message(f'metadata/valid/{w2p}')
        wcmp2_ids.append(_get_wcmp2_id_from_filename(w2p))
        time.sleep(5)

    time.sleep(10)

    for wcmp2_id in wcmp2_ids:
        assert wcmp2_id in CACHE_MESSAGES

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
    
