#! /usr/bin/python3
import paho.mqtt.client as mqtt
import ssl
import os,sys,time,platform
import io
import shutil
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import json
import uuid
from multiprocessing import Process

##Declaration
pub_client = None
LOG = None
pub_connected_flag = False

#############################
##### Funktionen   ##########
#############################

def init_log():
    global LOG
    logFile = "wis2-test_pub-trigger.log"
    logLevel = "INFO"
    loggerName = "wis2-test_pub-trigger"
    handlers = [ RotatingFileHandler(filename=logFile,
            mode='a',
            maxBytes=512000,
            backupCount=2)
           ]
    logging.basicConfig(handlers=handlers,
                    level=logLevel,
                    format='%(levelname)s %(asctime)s %(message)s',
                    datefmt='%Y%m%dT%H:%M:%S')
    LOG = logging.getLogger(loggerName)


def pub_connect(client, userdata, flags, rc, properties=None):
    global pub_connected_flag
    LOG.info(" - connected as: " + str(client))
    pub_connected_flag = True


def pub_disconnect(client, userdata, rc, properties=None):
    global pub_connected_flag
    pub_connected_flag = False
    LOG.info("----- connection closed for client: " + str(client) + " -----")


def get_pub_tls_connection(pub_mqtt_broker, pub_mqtt_tls_port, pub_clientname, pub_mqtt_user, pub_mqtt_password):
    pub_client = mqtt.Client(pub_clientname, protocol=mqtt.MQTTv5)
    pub_client.username_pw_set(pub_mqtt_user, password=pub_mqtt_password)
    pub_client.tls_set()
    pub_client.on_connect = pub_connect
    pub_client.on_disconnect = pub_disconnect
    pub_client.connect(pub_mqtt_broker,int(pub_mqtt_tls_port), properties=None)
    pub_client.loop_start()
    return pub_client


def publish_msg(pub_topic, jsonContent, org_filename):
    global pub_client
    try:
        info = pub_client.publish(pub_topic, jsonContent, qos=1)
        info.wait_for_publish()
        if info.is_published():
            LOG.info(" - PUBLISHED msg for: " + str(org_filename))
        else:
            LOG.error(" - NOT published for file: " + str(org_filename))
    except Exception:
        LOG.error(" - NOT published for file: " + str(org_filename))


def stop_trigger_pub():
    global pub_client
    pub_client.disconnect()
    pub_client.loop_stop()
    LOG.info(" ----- disconnected client: " + str(pub_client) + " -----")


def read_trigger_files():
    global LOG
    inMSG_Dir = "input/trigger"
    pub_topic = "config/a/wis2"
    # read trigger messages for pub
    if os.path.exists(inMSG_Dir):
        while True:
            pubFiles = [f for f in os.listdir(inMSG_Dir) if os.path.isfile(os.path.join(inMSG_Dir, f)) and not f.startswith('.')]
            if len(pubFiles) > 0:
                LOG.info("New trigger messages len() is: " + str(len(pubFiles)))
                for filename in pubFiles:
                    pub_file = os.path.join(inMSG_Dir, str(filename))
                    if os.path.exists(pub_file):
                        LOG.info("------ Next Message: " + str(pub_file))
                        # check json format via read, json.loads
                        with open(pub_file) as f:
                            data = f.read()
                        myInputMessage = json.loads(data)
                        msg_content = json.dumps(myInputMessage, indent=4)
                        LOG.info(msg_content)
                        publish_msg(pub_topic, msg_content, filename)
                    else:
                        LOG.warning(" - MISSING file for pub in filesystem: " + str(pub_file))
    else:
        LOG.warning("inMSG_Dir not found: ", str(inMSG_Dir))


def start_trigger_pub(pub_mqtt_broker, pub_mqtt_tls_port, pub_mqtt_user, pub_mqtt_password):
    global pub_client
    global LOG
    global pub_connected_flag
    pub_clientname_instanz = "wis2-test_pub-trigger"
    # init log
    init_log()
    LOG.info("--------------- SCRIPT RUN STARTED ----------------")
    # open connection
    LOG.info("----- start connection for client: " + str(pub_clientname_instanz) + " -----")
    pub_client = get_pub_tls_connection(pub_mqtt_broker, pub_mqtt_tls_port, pub_clientname_instanz, pub_mqtt_user, pub_mqtt_password)
    time.sleep(2)
    if pub_connected_flag:
        read_trigger = Process(target=read_trigger_files, args=())
        read_trigger.daemon = True
        read_trigger.start()
    else:
        LOG.error(" NOT connected, connected_flag is: " + str(connected_flag))
        pub_client.disconnect()
        pub_client.loop_stop()
