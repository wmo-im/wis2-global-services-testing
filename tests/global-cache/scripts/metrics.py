#! /usr/bin/python3
import requests
import json
from requests.auth import HTTPBasicAuth, HTTPDigestAuth


def ask_prometheus(myurl, user, password, prometheus_baseurl):
    req_exception = ""
    response = None
    response_status = 000
    retry = 0
    session = requests.Session()
    session.auth = (user, password)
    while retry < 3:
        try:
            auth = session.get(prometheus_baseurl)
            response = session.get(myurl)
            response_status = response.status_code
        except requests.exceptions.Timeout as con_ex:
            req_exception = "".join([" - http requests.exceptions.ConnectionError for ", str(myurl), "(retry ", str(retry), "): ", str(con_ex)])
            response = "http_except_error"
        except requests.exceptions.HTTPError as err:
            req_exception = "".join([" - http request error for ", str(myurl), "(retry ", str(retry), "): ", str(err)])
            response = "http_except_error"
        except requests.exceptions.RequestException as req_ex:
            req_exception = "".join([" - http request error for ", str(myurl), "(retry ", str(retry), "): ", str(req_ex)])
            response = "http_except_error"
        except:
            req_exception = "".join([" - http request error for ", str(myurl)])
            response = "http_except_error"
        if str(response_status).startswith("2"):
            break
        else:
            retry = retry + 1
    return response, response_status, req_exception
    # del
    del req_exception
    del response_status
    del response
    del retry


def get_prom_metric_value(metric_name, testnode_centre_id, test_gc_centre_id, prometheus_username, prometheus_password, prometheus_baseurl):
    metric_value = 0
    prometheus_api_part = "/api/v1/query?query="
    prom_query = metric_name + "{centre_id='" + testnode_centre_id + "',report_by='" + test_gc_centre_id + "'}%3E0"
    full_url = prometheus_baseurl + prometheus_api_part + prom_query
    response, response_status, req_exception = ask_prometheus(full_url, prometheus_username, prometheus_password, prometheus_baseurl)
    if req_exception == "" and str(response_status).startswith("2"):
        myResponse = json.loads(response.text)
        if len(myResponse["data"]["result"]) > 0 and "value" in myResponse["data"]["result"][0].keys():
            metric_value = myResponse["data"]["result"][0]["value"][1]
    return metric_value
