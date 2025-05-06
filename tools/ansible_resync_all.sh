#!/bin/sh

set -e
set -x

working_dir=`pwd`
cd WIS2\ Bench\ Tools/ansible-wis2-bench-tools/
sh install_wis2_bench_tools.sh

cd $working_dir

cd ./WIS2\ Notification\ Messages/ansible-wis2-traffic-generators/
sh install_wis2_traffic_nodes.sh

cd $working_dir

cd ./WIS2\ Data\ Generation/ansible-wis2-data-generators/
sh install_wis2_data_nodes.sh

