#!/bin/sh

set -e
set -x

working_dir=`pwd`
cd ./WIS2\ Notification\ Messages/ansible-wis2-traffic-generators/
sh remove_wis2_traffic_nodes.sh

cd $working_dir

cd ./WIS2\ Data\ Generation/ansible-wis2-data-generators/
sh remove_wis2_data_nodes.sh


