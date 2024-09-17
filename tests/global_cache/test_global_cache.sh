#!/bin/bash

# Load environment variables from global-cache.env
source ./global-cache.env

# Create the output directory if it doesn't exist
#OUTPUT_DIR=~/user/test-results/gc
OUTPUT_DIR="$HOME/results/${GC_METRICS_REPORT_BY}"
mkdir -p $OUTPUT_DIR

# Get the current datetime stamp
DATETIME=$(date '+%Y%m%d_%H%M%S')

# Construct the output file names
LOG_FILE="${OUTPUT_DIR}/gc_tests_${DATETIME}_${GC_METRICS_REPORT_BY}.log"
XML_FILE="${OUTPUT_DIR}/gc_tests_${DATETIME}_${GC_METRICS_REPORT_BY}.xml"

# Run the pytest and capture the output
pytest test_global_cache_functional.py --junitxml=$XML_FILE | tee $LOG_FILE