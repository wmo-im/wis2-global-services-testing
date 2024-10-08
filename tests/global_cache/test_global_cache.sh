#!/bin/bash

# Load environment variables from global-cache.env
source ./global-cache.env

# Create the output directory if it doesn't exist
#OUTPUT_DIR=~/user/test-results/gc
OUTPUT_DIR="/data/wis2-testing/results/${GC_METRICS_REPORT_BY}"
mkdir -p $OUTPUT_DIR

# Get the current datetime stamp
DATETIME=$(date '+%Y-%m-%dT%H:%M:%SZ')



# Construct the output file names
LOG_FILE="${OUTPUT_DIR}/gc_tests_${DATETIME}_${GC_METRICS_REPORT_BY}.log"
XML_FILE="${OUTPUT_DIR}/gc_tests_${DATETIME}_${GC_METRICS_REPORT_BY}.xml"

# Run the pytest and capture the output
echo -e "Running functional tests\n" | tee -a $LOG_FILE
pytest test_global_cache_functional.py --junitxml=$XML_FILE -l -rA --log-cli-level=DEBUG --log-cli-format='-%(funcName)s - %(message)s' --capture=tee-sys | tee -a $LOG_FILE
echo -e "Running performance tests\n" | tee -a $LOG_FILE
pytest test_global_cache_performance.py --junitxml=$XML_FILE -l -rA --log-cli-level=DEBUG --log-cli-format='-%(funcName)s - %(message)s' --capture=tee-sys | tee -a $LOG_FILE