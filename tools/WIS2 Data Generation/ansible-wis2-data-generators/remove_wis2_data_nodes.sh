#!/bin/bash

set -x

HOSTS=all

ansible-playbook -i inventory.yml site-remove.yml --limit $HOSTS
