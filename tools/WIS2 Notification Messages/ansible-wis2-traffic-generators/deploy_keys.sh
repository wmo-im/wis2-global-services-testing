#!/bin/bash

set -x

HOSTS=all

ansible-playbook -i inventory.yml site-sshkeys.yml --limit $HOSTS  --key-file "~/.ssh/id_rsa-wmotest"
