import uuid
from datetime import datetime
from random import random

from pywis_pubsub.mqtt import MQTTPubSubClient
from pywis_pubsub.publish import create_message


def check_broker_connectivity(connection_string: str):
    """
    Check if the broker is reachable
    :param connection_string:
    :return:
    """
    # return True if connection is successful, False otherwise
    is_connected = False
    pwclient = MQTTPubSubClient(connection_string)
    pwclient.conn.tls_insecure_set(True)  # Disable certificate verification
    pwclient.conn.loop()
    if pwclient.conn.is_connected():
        is_connected = True
    pwclient.conn.loop_stop()
    pwclient.conn.disconnect()
    del pwclient
    return is_connected


def generate_wnm(topic: str = None, msg_id: str = None, msg_dt: datetime = None, url: str = None,
                 content_type: str = None, msg_props: dict = None):
    if topic is None:
        topics = ["origin/a/wis2/+/data/#", "cache/a/wis2/+/data/#", "origin/a/wis2/+/metadata/#",
                  "cache/a/wis2/+/metadata/#"]
        # get random
        topic = topics[random.randint(0, len(topics) - 1)]
        # fill in the wildcards
        topic = topic.replace("+", str(uuid.uuid4()))
        topic = topic.replace("#", str(uuid.uuid4()))
    msg_dt = msg_dt.strftime('%Y-%m-%dT%H:%M:%S') + 'Z' if msg_dt is not None else datetime.utcnow().strftime(
        '%Y-%m-%dT%H:%M:%S') + 'Z'
    # msg_dt = msg_dt if msg_dt is not None else datetime.utcnow()
    message_args = {
        'topic': topic,
        'content_type': content_type,
        'url': "https://wis2-global-cache.s3.amazonaws.com/br-inmet/data/core/weather/surface-based-observations/synop/WIGOS_0-76-0-3106200000000597_20240822T140000.bufr4",
        'identifier': msg_id or str(uuid.uuid4()),
        'pubtime': msg_dt,  #
        # 'geometry': [33.8, -11.8, 123],
        # 'metadata_id': 'mock/metadata/identifier',
        # 'wigos_station_identifier': '0-20000-12345',
        # 'operation': 'create'
    }
    if msg_props:
        message_args.update(msg_props)
    message = create_message(**message_args)
    return topic, message
