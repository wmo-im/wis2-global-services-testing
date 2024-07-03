#!/bin/bash

set -x

HOSTS=all
HOSTS=ovhsingapour

ansible-playbook -i inventory.yml site.yml --limit $HOSTS
#ansible-playbook -i inventory.yml site.yml --limit $HOSTS --start-at-task "modify min value container01"
