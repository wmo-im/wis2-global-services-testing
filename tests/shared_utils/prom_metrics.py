import time
from prometheus_api_client import PrometheusConnect
import json
import base64


def fetch_prometheus_metrics(metric_name, prometheus_baseurl=None, username=None, password=None, report_by=None, centre_id=None):
    import base64
    from prometheus_api_client import PrometheusConnect

    # Ensure the base URL has a scheme
    if not prometheus_baseurl.startswith(("http://", "https://")):
        prometheus_baseurl = "https://" + prometheus_baseurl

    # Create headers for authentication if username and password are provided
    headers = {}
    if username and password:
        headers['Authorization'] = f'Basic {base64.b64encode(f"{username}:{password}".encode()).decode()}'

    # Connect to Prometheus
    prom = PrometheusConnect(url=prometheus_baseurl, headers=headers, disable_ssl=True)

    # Construct the query

    query = metric_name

    if report_by or centre_id:
        labels = []
        if report_by:
            labels.append(f'report_by="{report_by}"')
        if centre_id:
            labels.append(f'centre_id="{centre_id}"')

        query = f"{metric_name}{{{','.join(labels)}}}"

    # Fetch the metrics
    result = prom.custom_query(query=query)

    return result


def fetch_and_verify_metric(metric_name, expected_value, prometheus_baseurl, username, password):
    metrics = fetch_prometheus_metrics(metric_name, "", "", prometheus_baseurl, username, password)
    for metric in metrics:
        if metric['value'][1] != expected_value:
            raise AssertionError(f"Metric {metric_name} does not match expected value {expected_value}")


def fetch_and_verify_timestamp_metric(metric_name, expected_range, prometheus_baseurl, username, password):
    current_time = time.time()
    metrics = fetch_prometheus_metrics(metric_name, "", "", prometheus_baseurl, username, password)
    for metric in metrics:
        timestamp = float(metric['value'][1])
        if not (current_time - expected_range <= timestamp <= current_time):
            raise AssertionError(f"Metric {metric_name} timestamp {timestamp} is not within the expected range")


if __name__ == '__main__':
    # Example usage
    from dotenv import load_dotenv
    import os

    load_dotenv("./global-cache.env")
    load_dotenv("../secrets.env")
    load_dotenv("../default.env")
    # prometheus config
    prometheus_baseurl = os.getenv('PROMETHEUS_HOST')
    username = os.getenv('PROMETHEUS_USER')
    password = os.getenv('PROMETHEUS_PASSWORD')
    # print the credentials
    print(f"Prometheus credentials: {username}:{password}")
    print(prometheus_baseurl)
    metric_name = "wmo_wis2_gc_downloaded_total"
    report_by = os.getenv('GC_METRICS_REPORT_BY')
    print(report_by)
    centre_id = "io-wis2dev-11-test"

    metrics = fetch_prometheus_metrics(metric_name, report_by, centre_id, prometheus_baseurl, username, password)
    print(json.dumps(metrics, indent=4))
