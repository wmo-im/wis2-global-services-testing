from pywis_pubsub.mqtt import MQTTPubSubClient


def check_broker_connectivity(connection_string:str):
    # return True if connection is successful, False otherwise
    is_connected = False
    pwclient = MQTTPubSubClient(connection_string)
    pwclient.conn.loop()
    if pwclient.conn.is_connected():
        is_connected = True
    pwclient.conn.loop_stop()
    pwclient.conn.disconnect()
    del pwclient
    return is_connected