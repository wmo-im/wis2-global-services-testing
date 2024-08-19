#!/bin/bash

set -x

HOSTS=all
#HOSTS=ovhsingapour
#HOSTS=awstestnode01,awstestnode02

ansible-playbook -i inventory.yml site.yml --limit $HOSTS
#ansible-playbook -i inventory.yml site.yml --limit $HOSTS --start-at-task "modify min value container01"
