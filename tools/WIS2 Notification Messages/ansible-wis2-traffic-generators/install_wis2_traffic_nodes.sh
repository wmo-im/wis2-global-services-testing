#!/bin/bash

set -x

HOSTS=all
#HOSTS=ovhsydney

ansible-playbook -i inventory.yml site.yml --limit $HOSTS
#ansible-playbook -i inventory.yml site.yml --limit $HOSTS --start-at-task "modify min value container01"
#ansible-playbook -i inventory.yml site.yml --limit $HOSTS --start-at-task "copy Docker Compose files"
#ansible-playbook -i inventory.yml site.yml --limit $HOSTS --start-at-task "data add-collection synops"
