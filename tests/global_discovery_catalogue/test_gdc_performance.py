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

import logging
import os
import sys
import time

import requests

sys.path.append('.')

from global_discovery_catalogue.test_gdc_functional import (
    _get_wcmp2_id_from_filename,
    _publish_wcmp2_trigger_broker_message,
    _subscribe_gb_client,
    gb_client,
    sleep_factor
)


LOGGER = logging.getLogger(__name__)

GDC_API = os.environ['GDC_API']

METADATA_DIR = os.path.join(os.path.dirname(__file__), 'metadata')


def test_api_functionality(sleep_factor, gb_client):
    print('Testing API functionality')

    assert gb_client.conn.is_connected

    _subscribe_gb_client(gb_client)

    time.sleep(1 * sleep_factor)

    assert gb_client.conn.subscribed_flag

    start = time.time()

    wcmp2_ids = []
    for w2p in os.listdir(f'{METADATA_DIR}/valid'):
        _publish_wcmp2_trigger_broker_message(f'metadata/valid/{w2p}')
        wcmp2_ids.append(_get_wcmp2_id_from_filename(w2p))
        time.sleep(5 * sleep_factor)

    time.sleep(10 * sleep_factor)

    end = time.time()

    sleep_total = len(wcmp2_ids) + 10

    elapsed = (end - start) - (sleep_total * sleep_factor)

    run_api_tests()

    assert elapsed < (300 * sleep_factor)


def run_api_tests():
    print('Query GDC API')

    base_url = GDC_API

    query_url = None

    LOGGER.info('Querying base collection endpoint')
    r = requests.get(base_url).json()

    for link in r['links']:
        if all([link.get('rel') == 'items',
                link.get('type') == 'application/geo+json']):
            query_url = link['href']
            break

    assert query_url is not None

    LOGGER.info('Querying items endpoint')
    r = requests.get(query_url).json()

    assert r['numberMatched'] == 6
    assert r['numberReturned'] == 6
