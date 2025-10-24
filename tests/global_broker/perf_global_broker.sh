#!/bin/bash

# Load environment variables from global-cache.env
source ./global-broker.env

# Create the output directory if it doesn't exist
#OUTPUT_DIR=~/user/test-results/gc
OUTPUT_DIR="/data/wis2-testing/results/${GB_METRICS_REPORT_BY}"
mkdir -p $OUTPUT_DIR

# Get the current datetime stamp
DATETIME=$(date '+%Y-%m-%dT%H:%M:%SZ')



# Construct the output file names
LOG_FILE="${OUTPUT_DIR}/gb_tests_${DATETIME}_${GB_METRICS_REPORT_BY}.log"
XML_FILE="${OUTPUT_DIR}/gb_tests_${DATETIME}_${GB_METRICS_REPORT_BY}.xml"


if [[ ${1} == "Low" ]]
then
  pytest gb_performance_tests.py -k test_1_mqtt_broker_lowperf -v -s --junitxml=$XML_FILE -l -rA | tee $LOG_FILE
elif [[ ${1} == "Medium" ]]
then
  pytest gb_performance_tests.py -k test_2_mqtt_broker_medperf -v -s --junitxml=$XML_FILE -l -rA | tee $LOG_FILE
elif [[ ${1} == "High" ]]
then
  pytest gb_performance_tests.py -k test_3_mqtt_broker_highperf -v -s --junitxml=$XML_FILE -l -rA | tee $LOG_FILE
elif [[ ${1} == "Extreme" ]]
then
  pytest gb_performance_tests.py -k test_4_mqtt_broker_extremeperf -v -s --junitxml=$XML_FILE -l -rA | tee $LOG_FILE
elif [[ ${1} == "Heroique" ]]
then
  pytest gb_performance_tests.py -k test_5_mqtt_broker_heroicperf -v -s --junitxml=$XML_FILE -l -rA | tee $LOG_FILE
else
  echo "usage $0 [Low | Medium | High | Extreme | Heroique]"
fi

