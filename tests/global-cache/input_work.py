#! /usr/bin/python3
import paho.mqtt.client as mqtt
import ssl
import os,sys,time
from datetime import datetime
from time import sleep
import uuid
import queue
from connection_subscription import input_queue, stop_event
from download import download, ask_url, calc_integrity
import json
import threading
from multiprocessing import Process, Pipe, Manager

# Declaration
already_downloaded = []
msg_store_origin = "./output/msg_store_origin"
msg_store_cache = "./output/msg_store_cache"
msgTest_cache = {}
msgTest_origin = {}
downloadDir = "./output/downloads"
compareDir = "./output/compare"
inWork = []
lock = threading.Lock()
integrity_ok = []
integrity_error = []
cache_msg_ok = []
cache_msg_error = []
cache_msg_missing = []
no_cache = []
amount_threads_read_input = 2


def compare_msg(data_id):
    global msgTest_origin, msgTest_cache
    global cache_msg_ok, cache_msg_error, cache_msg_missing
    file_content = ""
    data_id_filename = data_id.replace("/","_")
    compareFile = os.path.join(compareDir, data_id_filename)
    target_diff_fields = ["id", "href"]
    diff_fields = []
    missed_diff = []
    additional_diffs = []
    status = "NOT SET"
    msg_id = ""
    if data_id in msgTest_cache.keys():
        for mykey in msgTest_origin[data_id].keys():
            if not mykey in msgTest_cache[data_id].keys():
                file_content = "MISSING " + str(mykey) + " in cache msg keys " + str(msgTest_cache[data_id].keys())
                if not mykey in diff_fields:
                    diff_fields.append(mykey)
            else:
                if mykey == "properties":
                    for propertiesKey in msgTest_origin[data_id]["properties"].keys():
                        if msgTest_origin[data_id]["properties"][propertiesKey] != msgTest_cache[data_id]["properties"][propertiesKey]:
                            file_content = "".join([file_content, "\nDIFFS in ", str(propertiesKey), " (origin\n", str(msgTest_origin[data_id]["properties"][propertiesKey]), "\ncache \n", str(msgTest_cache[data_id]["properties"][propertiesKey])])
                            if not propertiesKey in diff_fields:
                                diff_fields.append(propertiesKey)
                        else:
                            file_content = "".join([file_content, "\nSAME value under properties for ",str(propertiesKey)])
                else:
                    if mykey == "links":
                        for i in range(len(msgTest_origin[data_id]["links"])):
                            for linksKey in msgTest_origin[data_id]["links"][i].keys():
                                if msgTest_origin[data_id]["links"][i][linksKey] != msgTest_cache[data_id]["links"][i][linksKey]:
                                    file_content = "".join([file_content, "\nDIFFS in link ", str(i), " in ", str(linksKey), " (origin\n", str(msgTest_origin[data_id]["links"][i][linksKey]), "\ncache \n", str(msgTest_cache[data_id]["links"][i][linksKey])])
                                    if not linksKey in diff_fields:
                                        diff_fields.append(linksKey)
                                else:
                                    file_content = "".join([file_content, "\nSAME value under links in link ", str(i), " for ", str(linksKey)])
                    else:
                        if msgTest_origin[data_id][mykey] != msgTest_cache[data_id][mykey]:
                            file_content = "".join([file_content, "\nDIFFS in ", str(mykey), " (origin\n", str(msgTest_origin[data_id][mykey]), "\ncache\n", str(msgTest_cache[data_id][mykey])])
                            if not mykey in diff_fields:
                                diff_fields.append(mykey)
        for item in target_diff_fields:
            if not item in diff_fields:
                missed_diff.append[item]
        for item in diff_fields:
            if not item in target_diff_fields:
                additional_diffs.append(item)
        if len(missed_diff) == 0 and len(additional_diffs) == 0:
            if not msgTest_cache[data_id]["id"] in cache_msg_ok:
                cache_msg_ok.append(msgTest_cache[data_id]["id"])
        else:
            if not msgTest_cache[data_id]["id"] in cache_msg_error:
                cache_msg_error.append(msgTest_cache[data_id]["id"])
        with open(compareFile, "w") as comFile:
            comFile.write(file_content)
            comFile.write("missed_diff: " + str(missed_diff))
            comFile.write("additional_diffs: " + str(additional_diffs))
    else:
        if not msgTest_origin[data_id]["id"] in cache_msg_missing:
            cache_msg_missing.append(msgTest_origin[data_id]["id"])


def read_input_queue():
    global input_queue
    global already_downloaded
    global msgTest_origin, msgTest_cache
    global integrity_ok, integrity_error
    global no_cache
    global inWork
    global stop_event
    while not stop_event.is_set():
        while not input_queue.empty():
            # declaration
            data_id = ""
            msg_item = ""
            msg_topic = ""
            new_msg = ""
            url = ""
            downloadFile = ""
            download_process = None
            error_message = ""
            exception_text = ""
            download_error_file = ""
            if not input_queue.empty():
                # get next item from input_queue
                try:
                    msg_item = input_queue.get()
                    msg_topic, new_msg = msg_item.split(";", 1)
                    input_queue.task_done()
                except get_input_queue_ex:
                    exception_text = ''.join(["read_input_queue: exception get_input_queue_ex ", str(get_input_queue_ex)])
                if msg_topic != "" and new_msg != "":
                    try:
                        # readMSG
                        myMessage = json.loads(new_msg)
                        msg_id = myMessage["id"]
                        data_id = myMessage["properties"]["data_id"]
                        if not data_id in inWork:
                            with lock:
                                inWork.append(data_id)
                            download_error_file = os.path.join(downloadDir, "".join(["error_", data_id]))
                            # write msg_store and put to arrays
                            if "origin/a/" in msg_topic:
                                myFile = os.path.join(msg_store_origin, msg_id)
                                if not data_id in msgTest_origin.keys():
                                    msgTest_origin[data_id] = myMessage
                            else:
                                myFile = os.path.join(msg_store_cache, msg_id)
                                if not data_id in msgTest_cache.keys():
                                    msgTest_cache[data_id] = myMessage
                            with open(myFile, "w") as myMSG_File:
                                myMSG_File.write(msg_topic + "\n" + json.dumps(new_msg, indent=4))
                            # no cache
                            if "cache" in myMessage["properties"].keys():
                                cache = bool(myMessage["properties"]["cache"])
                            else:
                                cache = True
                            if cache is False:
                                if not data_id in no_cache:
                                    no_cache.append(data_id)
                            # download values
                            for i in range(len(myMessage["links"])):
                                if myMessage["links"][i]["rel"] == "canonical":
                                    url = myMessage["links"][i]["href"]
                            if url != "":
                                filename = os.path.basename(url)
                                downloadFile = os.path.join(downloadDir, filename)
                            if not data_id in already_downloaded and "cache/a/" in msg_topic:
                                # download
                                download_error = False
                                if url != "" and downloadFile != "":
                                    try:
                                        manager = Manager()
                                        return_dict = manager.dict()
                                        download_process = Process(target=download, args=(data_id, url, downloadFile, return_dict))
                                        download_process.daemon = True
                                        download_process.start()
                                        download_process.join(timeout=360)
                                        if "download_error" in return_dict.keys():
                                            download_error = return_dict["download_error"]
                                        if download_error is True:
                                            if "error_message" in return_dict.keys():
                                                error_message = return_dict["error_message"]
                                            if os.path.isfile(downloadFile):
                                                try:
                                                    os.remove(downloadFile)
                                                except Exception as rm_file_ex:
                                                    exception_text = ''.join([exception_text, ", download_error is True, rm_file_ex ", str(rm_file_ex)])
                                        else:
                                            already_downloaded.append(data_id)
                                            # check integrity
                                            integrity_method = myMessage["properties"]["integrity"]["method"]
                                            integrity_value = myMessage["properties"]["integrity"]["value"]
                                            file_integrity, error_file_integrity = calc_integrity(downloadFile, integrity_method)
                                            if file_integrity[0] == integrity_value or integrity_value == "" or file_integrity[1] == integrity_value:
                                                if not downloadFile in integrity_ok:
                                                    integrity_ok.append(downloadFile)
                                            else:
                                                if not downloadFile in integrity_error:
                                                    integrity_error.append(downloadFile)
                                    except Exception as process_ex:
                                        exception_text = ''.join([exception_text, ", process_ex " + str(process_ex)])
                                        download_error = True
                                    if download_error is True:
                                        with open(download_error_file, "w") as errFile:
                                            errFile.write("download error for url " + str(url) + " with error_message " + str(error_message))
                                            if exception_text != "":
                                                errFile.write("exception_text: " + str(exception_text))

                    except Exception as readMSG_ex:
                        exception_text = ''.join([exception_text, ", readMSG_ex ", str(readMSG_ex)])
                    with lock:
                        if data_id in inWork:
                            inWork.remove(data_id)
                    sleep(0.2)
                else:
                    # msg_topic or new_msg == ""
                    sleep(0.2)
            else:
                # input_queue is empty
                sleep(1)
            # del
            del data_id
            del msg_item
            del msg_topic
            del new_msg
            del url
            del downloadFile
    print(" - read_input_queue thread stopped")


def start_thread_read_input_queue():
    thread_counter_read_input = 0
    while thread_counter_read_input < int(amount_threads_read_input):
            input_thread = threading.Thread(target=read_input_queue, daemon=True)
            input_thread.start()
            thread_counter_read_input = thread_counter_read_input + 1
    print("-- Threads for read_input_queue started")
