import re
import json
import traceback

def parse_ab_output(ab_output):
    result = {}
    patterns = [
        ('Server Software', r'Server Software:\s+(\S+)'),
        ('Server Hostname', r'Server Hostname:\s+(\S+)'),
        ('Server Port', r'Server Port:\s+(\d+)'),
        ('SSL/TLS Protocol', r'SSL/TLS Protocol:\s+(.+)'),
        ('Server Temp Key', r'Server Temp Key:\s+(.+)'),
        ('TLS Server Name', r'TLS Server Name:\s+(\S+)'),
        ('Document Path', r'Document Path:\s+(\S+)'),
        ('Document Length', r'Document Length:\s+(\d+)'),
        ('Concurrency Level', r'Concurrency Level:\s+(\d+)'),
        ('Time taken for tests', r'Time taken for tests:\s+([\d.]+)'),
        ('Complete requests', r'Complete requests:\s+(\d+)'),
        ('Failed requests', r'Failed requests:\s+(\d+)'),
        ('Total transferred', r'Total transferred:\s+(\d+)'),
        ('HTML transferred', r'HTML transferred:\s+(\d+)'),
        ('Requests per second', r'Requests per second:\s+([\d.]+)'),
        ('Time per request', r'Time per request:\s+([\d.]+) \[ms\] \(mean\)'),
        ('Time per request (across all concurrent requests)', r'Time per request:\s+([\d.]+) \[ms\] \(mean, across all concurrent requests\)'),
        ('Transfer rate', r'Transfer rate:\s+([\d.]+) \[Kbytes/sec\] received')
    ]

    for key, pattern in patterns:
        try:
            result[key] = re.search(pattern, ab_output).group(1)
        except AttributeError:
            print(traceback.format_exc())
            pass
    try:
        connection_times = re.search(r'Connection Times \(ms\)\s+min\s+mean\[\+/-sd\]\s+median\s+max\nConnect:\s+(\d+)\s+(\d+)\s+([\d.]+)\s+(\d+)\s+(\d+)\nProcessing:\s+(\d+)\s+(\d+)\s+([\d.]+)\s+(\d+)\s+(\d+)\nWaiting:\s+(\d+)\s+(\d+)\s+([\d.]+)\s+(\d+)\s+(\d+)\nTotal:\s+(\d+)\s+(\d+)\s+([\d.]+)\s+(\d+)\s+(\d+)', ab_output)
        result['Connection Times'] = {
            'Connect': {
                'min': connection_times.group(1),
                'mean': connection_times.group(2),
                'sd': connection_times.group(3),
                'median': connection_times.group(4),
                'max': connection_times.group(5)
            },
            'Processing': {
                'min': connection_times.group(6),
                'mean': connection_times.group(7),
                'sd': connection_times.group(8),
                'median': connection_times.group(9),
                'max': connection_times.group(10)
            },
            'Waiting': {
                'min': connection_times.group(11),
                'mean': connection_times.group(12),
                'sd': connection_times.group(13),
                'median': connection_times.group(14),
                'max': connection_times.group(15)
            },
            'Total': {
                'min': connection_times.group(16),
                'mean': connection_times.group(17),
                'sd': connection_times.group(18),
                'median': connection_times.group(19),
                'max': connection_times.group(20)
            }
        }
    except AttributeError:
        print(traceback.format_exc())
        pass

    try:
        percentage_times = re.findall(r'(\d+)%\s+(\d+)', ab_output)
        result['Percentage of requests served within a certain time'] = {f'{percent}%': time for percent, time in percentage_times}
    except AttributeError:
        print(traceback.format_exc())
        pass

    return result

with open("ab_1.txt", "r") as file:
    ab_output = file.read()
    ab_json = parse_ab_output(ab_output)
    print(ab_json)