#! /usr/bin/python3
import os,sys,time
from datetime import datetime
import requests
import json
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from time import sleep
from connection_subscription import *
from metrics import ask_prometheus, get_prom_metric_value
from input_work import *
from pub_trigger import *
import queue
import threading


## Declaration
# to be set
testnode_centre_id = ""
test_gc_broker = ""
test_gc_broker_port = 8883
test_gc_broker_user = ""
test_gc_broker_passwd = ""
test_gc_centre_id = ""
prometheus_baseurl = ""
prometheus_username = ""
prometheus_password = ""
pub_mqtt_user = ""
pub_mqtt_password = ""

my_scenario1 = "input/scenario1"
connected_flag = False
subscribed_flag = False
sub_error = ""
test_connection_topic = "cache/a/wis2/#"
sub_topic = "+/a/wis2/" + testnode_centre_id + "/#"
now = datetime.now()
script_starttime = now.strftime('%Y-%m-%dT%H:%M:%S')
inWork = []
downloaded_total_before = 0
downloaded_errors_total_before = 0
downloaded_total_after = 0
downloaded_errors_total_after = 0
downloaded_total_diff = 0
downloaded_errors_total_diff = 0
dataserver_status_flag_before = 0
dataserver_status_flag_after = 0


## Functions
def run_scenario():
    print("- STEP 01 - metrics_collector (before test run):")
    # wmo_wis2_gc_downloaded_total
    downloaded_total_before = get_prom_metric_value("wmo_wis2_gc_downloaded_total", testnode_centre_id, test_gc_centre_id, prometheus_username, prometheus_password, prometheus_baseurl)
    print("-- BEFORE - downloaded_total{centre_id='" + testnode_centre_id + "'}: " + str(downloaded_total_before))
    # wmo_wis2_gc_downloaded_errors_total
    downloaded_errors_total_before = get_prom_metric_value("wmo_wis2_gc_downloaded_errors_total", testnode_centre_id, test_gc_centre_id, prometheus_username, prometheus_password, prometheus_baseurl)
    print("-- BEFORE - downloaded_errors_total{centre_id='" + testnode_centre_id + "'}: " + str(downloaded_errors_total_before))
    # wmo_wis2_gc_dataserver_status_flag
    dataserver_status_flag_before = get_prom_metric_value("wmo_wis2_gc_dataserver_status_flag", testnode_centre_id, test_gc_centre_id, prometheus_username, prometheus_password, prometheus_baseurl)
    print("-- BEFORE - dataserver_status_flag{centre_id='" + testnode_centre_id + "'}: " + str(dataserver_status_flag_before))

    print("\n- STEP 02 - Start Subscription for topic " + str(sub_topic))
    start_thread_read_input_queue()
    sleep(1)
    status, sub_status, error_message = start_subscription(test_gc_broker, test_gc_broker_port, test_gc_broker_user, test_gc_broker_passwd, sub_topic)
    while not stop_event.is_set():
        sleep(1)
    sleep(5)

    print("\n- STEP 03 - metrics_collector (after test run):")
    # wmo_wis2_gc_downloaded_total
    downloaded_total_after = get_prom_metric_value("wmo_wis2_gc_downloaded_total", testnode_centre_id, test_gc_centre_id, prometheus_username, prometheus_password, prometheus_baseurl)
    print("-- AFTER - downloaded_total{centre_id='" + testnode_centre_id + "'}: " + str(downloaded_total_after))
    # wmo_wis2_gc_downloaded_errors_total
    downloaded_errors_total_after = get_prom_metric_value("wmo_wis2_gc_downloaded_errors_total", testnode_centre_id, test_gc_centre_id, prometheus_username, prometheus_password, prometheus_baseurl)
    print("-- AFTER - downloaded_errors_total{centre_id='" + testnode_centre_id + "'}: " + str(downloaded_errors_total_after))
    # wmo_wis2_gc_dataserver_status_flag
    dataserver_status_flag_after = get_prom_metric_value("wmo_wis2_gc_dataserver_status_flag", testnode_centre_id, test_gc_centre_id, prometheus_username, prometheus_password, prometheus_baseurl)
    print("-- AFTER - dataserver_status_flag{centre_id='" + testnode_centre_id + "'}: " + str(dataserver_status_flag_after))

    # diff
    downloaded_total_diff = int(downloaded_total_after) - int(downloaded_total_before)
    downloaded_errors_total_diff = int(downloaded_errors_total_after) - int(downloaded_errors_total_before)
    print("\n-- DIFF - downloaded_total{centre_id='" + testnode_centre_id + "'}: " + str(downloaded_total_diff))
    print("-- DIFF - downloaded_errors_total{centre_id='" + testnode_centre_id + "'}: " + str(downloaded_errors_total_diff))


## Main
# makedirs
msg_store_origin = "./output/msg_store_origin"
if not os.path.exists(msg_store_origin):
    os.makedirs(msg_store_origin, exist_ok=True)
msg_store_cache = "./output/msg_store_cache"
if not os.path.exists(msg_store_cache):
    os.makedirs(msg_store_cache, exist_ok=True)
downloadDir = "./output/downloads"
if not os.path.exists(downloadDir):
    os.makedirs(downloadDir, exist_ok=True)
compareDir = "./output/compare"
if not os.path.exists(compareDir):
    os.makedirs(compareDir, exist_ok=True)

print("##### 8.1. Functional Tests #####")
print("\nSTARTED: " + str(script_starttime))
print(" - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ")
# 8.1.1. 1.
print("\n8.1.1. 1. MQTT Broker Connectivity")
status, sub_status, error_message = connection_test(test_gc_broker, test_gc_broker_port, test_gc_broker_user, test_gc_broker_passwd, test_connection_topic)
print("Evaluate connection result:      " + str(status))
print(" - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ")

# 8.1.2. 2.
print("\n8.1.2. 2. GC MQTT Broker Subscription")
if sub_status == "SUCCESS":
    print("Evaluate subscription result:    " + str(sub_status))
else:
    print("Evaluate subscription result:    " + str(sub_status) + ", error_message " + str(error_message))
print(" - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ")

# 8.1.3. 3.
print("\n8.1.3. 3. WIS2 Notification Message (WNM) Processing")
print("RUN TEST SCENARIO 1")
my_scenario = my_scenario1
start_trigger_pub(test_gc_broker, test_gc_broker_port, pub_mqtt_user, pub_mqtt_password)
run_scenario()
print("\nA) Evaluate WNM Messages:")
print("- STEP 1 - total number of cache notification messages published by the GC: " + str(len(msgTest_cache)))
print("- STEP 2 - Compare received origin and cache messages: \nlen(msgTest_origin) " + str(len(msgTest_origin.keys())) + ", len(msgTest_cache) " + str(len(msgTest_cache.keys())))
for data_id in msgTest_origin.keys():
    status = compare_msg(data_id)
if len(cache_msg_missing) != 0:
    print(" - for following origin messages the cache message is missing: " + str(cache_msg_missing))
if len(cache_msg_error) == 0:
    print(" - all origin messages compared to their cache messages are OK")
else:
    print(" - following messages are NOT OK (see compare file for details): " + str(cache_msg_error))

print("\nB) Data Objects:")
if len(msgTest_cache) == int(int(downloaded_total_diff) + len(no_cache)):
    total_number_msg_status = "OK"
else:
    total_number_msg_status = "ERROR"
print("- STEP 1 - total number of data objects cached by the GC same as published cache msg: " + str(total_number_msg_status) + "\n(len(msgTest_cache) is " + str(len(msgTest_cache)) + ", len(no_cache) is " + str(len(no_cache)) + ", int(downloaded_total_diff) is " + str(downloaded_total_diff) + ")")
if len(integrity_error) == 0:
    print("- STEP 2 - data objects cached by the GC identical to the source data objects: TRUE")
else:
    print("- STEP 2 - data objects cached by the GC identical to the source data objects: FALSE, different for " + str(integrity_error))

print(" - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ")
print("\n8.1.4. 4. Cache False Directive")
print("RUN TEST SCENARIO 2")
stop_trigger_pub()
