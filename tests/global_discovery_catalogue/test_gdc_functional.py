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

import os
import time

from dotenv import load_dotenv
import paho.mqtt.client as mqtt
import pytest
from pywis_pubsub.mqtt import MQTTPubSubClient

load_dotenv('default.env')

TOPIC = 'cache/a/wis2/+/metadata/#'


@pytest.fixture
def gb_client():
    options = {
        'client_id': 'wis2-gdc-test-runner'
    }
    return MQTTPubSubClient(os.environ['GB'], options)


def _on_subscribe(client, userdata, mid, reason_codes, properties):
    client.subscribed_flag = True


def test_gb_subscription(gb_client):
    assert gb_client.conn.is_connected
    gb_client.conn.subscribed_flag = False
    gb_client.conn.on_subscribe = _on_subscribe
    gb_client.conn.loop_start()
    result, mid = gb_client.conn.subscribe(TOPIC)
    time.sleep(1)
    assert result is mqtt.MQTT_ERR_SUCCESS
    assert gb_client.conn.subscribed_flag
    gb_client.conn.loop_stop()
    gb_client.conn.disconnect()
