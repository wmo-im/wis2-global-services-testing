import os, os.path, ssl
from pathlib2 import Path
from datetime import datetime, timedelta
from time import time
import hashlib
from urllib.parse import urlparse
import threading
import copy
import resource
import psutil
from time import sleep
from base64 import b64decode, b64encode
from uuid import uuid1
import requests


def ask_url(myurl, retry):
    req_exception = ""
    response = None
    response_status = 000
    try:
        response = requests.get(myurl, stream=True)
        response_status = response.status_code
    except requests.exceptions.Timeout as con_ex:
        req_exception = "".join([" - http requests.exceptions.ConnectionError for ", str(myurl), "(retry ", str(retry), "): ", str(con_ex)])
        response = "http_except_error"
    except requests.exceptions.HTTPError as err:
        req_exception = "".join([" - http request error for ", str(myurl), "(retry ", str(retry), "): ", str(err)])
        response = "http_except_error"
    except requests.exceptions.RequestException as other_err:
        req_exception = "".join([" - http request error for ", str(myurl), " other_err ", str(other_err)])
        response = "http_except_error"
    return response, response_status, req_exception
    # del
    del req_exception
    del response_status
    del response


def download(data_id, url, downloadFile, return_dict):
    # declaration
    download_error = True
    error_message = ""
    max_download_size = 1073741824     # 1GB
    max_retries_download = 3
    req_exc = ""
    reqStatus = 000
    response = ""
    retry = 1
    # http request
    for retry in range(max_retries_download):
        try:
            response, reqStatus, req_exc = ask_url(url, retry)
            if reqStatus != 200:
                error_message = "".join([" - download: reqStatus is ", str(reqStatus)])
                download_error = True
            else:
                if not len(response.text) > 0:
                    error_message = "".join([" - download: len(response.text) is 0"])
                    download_error = True
                else:
                    error_message = ""
                    download_error = False
                    break
        except Exception as ask_url_ex:
            error_message = "".join([" - download: request exception: ", str(ask_url_ex)])
            download_error = True
    # http request ready
    # write response to file
    if download_error is False and not str(response) == "":
        try:
            if not os.path.isfile(downloadFile):
                try:
                    content_size = 0
                    with open(downloadFile, 'wb') as out_tmp_file:
                        for chunk in response.iter_content(chunk_size=8192):   # 8MB
                            content_size = content_size + 8192
                            if int(content_size) < int(max_download_size):
                                out_tmp_file.write(chunk)
                            else:
                                error_message = "".join([" - download: no Content-Length set, iter_content reached max_download_size for ", str(url)])
                                download_error = True
                                break
                except Exception as wrote_tmp_file_ex:
                    error_message = "".join([" - download: wrote_tmp_file_ex ", str(wrote_tmp_file_ex), " error_message is ", str(error_message)])
                    download_error = True
            else:
                # file already exists
                error_message = "".join([" - download: write response to file - file already exists ", tmp_file])
                download_error = True
        except Exception as write_file_ex:
            download_error = True
            error_message = "".join([" - download: write_file_ex ", str(write_file_ex)])
    # download ready
    return_dict["download_error"] = download_error
    return_dict["error_message"] = error_message
    # del variables
    if not response is None:
        del response
    del req_exc
    del error_message
    del download_error
    del retry
    del reqStatus
    del max_retries_download
    del max_download_size


def calc_integrity(filename, integrity_method):
    file_content = None
    file_integrity = ["",""]
    h = None
    file_integrity_hexdigest = ""
    file_integrity_b64 = ""
    error_file_integrity = ""
    if not os.path.isfile(filename):
        error_file_integrity = "".join([" - calc_integrity: missing file ", str(filename)])
        file_content = None
    else:
        if os.path.basename(filename) == "" or os.path.basename(filename) is None:
            error_file_integrity = "".join([" - calc_integrity:  missing filename: ", os.path.basename(filename)])
            file_content = None
        else:
            try:
                with open(filename, 'rb') as inFile:
                    file_content = inFile.read()
            except:
                error_file_integrity = "".join([" - calc_integrity: missing file: ", str(filename)])
                file_content = None
            if ("sha512" in integrity_method or "SHA512" in integrity_method):
                h = hashlib.sha512()
            else:
                if ("sha384" in integrity_method or "SHA384" in integrity_method):
                    h = hashlib.sha384()
                else:
                    if ("sha256" in integrity_method or "SHA256" in integrity_method):
                        h = hashlib.sha256()
                    else:
                        if ("sha3-512" in integrity_method or "SHA3-512" in integrity_method):
                            h = hashlib.sha3_512()
                        else:
                            if ("sha3-384" in integrity_method or "SHA3-384" in integrity_method):
                                h = hashlib.sha3_384()
                            else:
                                if ("sha3-256" in integrity_method or "SHA3-256" in integrity_method):
                                    h = hashlib.sha3_256()
                                else:
                                    error_file_integrity = "".join([" - calc_integrity: integrity_method ('", integrity_method, "') not known, filename: ", filename])
        if h is not None:
            if not file_content is None:
                h.update(file_content)
                file_integrity_hexdigest = str(h.hexdigest())
                file_integrity_b64 = b64encode(h.digest()).decode("utf-8")
                file_integrity = [ file_integrity_hexdigest, file_integrity_b64 ]
            else:
                error_file_integrity = "".join([" - calc_integrity: no file_content for file: ", filename])
                file_integrity = "None"
        else:
            file_integrity = "None"
    return file_integrity, error_file_integrity
    # del
    del file_integrity
    del file_content
    del h
    del file_integrity_hexdigest
    del file_integrity_b64
    del error_file_integrity
