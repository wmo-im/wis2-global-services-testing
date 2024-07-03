# WIS2 Global Services testing - Ansible playbook to implement data generators

## Overview

This document provides detailed information to install data generators via Ansible.

## Dependencies

### Rocky Linux 8 on the target hosts

It is expected that target hosts are running Rocky8 (but the playbooks may be adapted to suit other linux flavours)

### Ansible

Ansible on the Ansible orchestrator (where the playbooks are played from)
```bash
apt install ansible
```
### Docker collection for ansible

The community.docker collection is mandatory:

```bash
$ ansible-galaxy collection install community.docker
Starting galaxy collection install process
Process install dependency map
Starting collection install process
Installing 'community.docker:3.10.4' to '/home/casa/.ansible/collections/ansible_collections/community/docker'
Downloading https://galaxy.ansible.com/api/v3/plugin/ansible/content/published/collections/artifacts/community-docker-3.10.4.tar.gz to /home/casa/.ansible/tmp/ansible-local-27484h_yoy2eb/tmphzodvhll
community.docker (3.10.4) was installed successfully
Installing 'community.library_inventory_filtering_v1:1.0.1' to '/home/casa/.ansible/collections/ansible_collections/community/library_inventory_filtering_v1'
Downloading https://galaxy.ansible.com/api/v3/plugin/ansible/content/published/collections/artifacts/community-library_inventory_filtering_v1-1.0.1.tar.gz to /home/casa/.ansible/tmp/ansible-local-27484h_yoy2eb/tmphzodvhll
community.library_inventory_filtering_v1 (1.0.1) was installed successfully
`` 

Failure to install this module may lead to exectution messages such as: 
```
ERROR! couldn't resolve module/action 'community.docker.docker_compose_v2'. This often indicates a misspelling, missing collection, or incorrect module path.
```

## Deployment

### Sites definition

The target hosts are defined under the inventory.yml.

For example:
```bash
$ cat inventory.yml 
all:
  children:
    wis2datanodes:
      hosts:
        ovhsingapour:
          ansible_host: 51.79.248.212
          ansible_user: rocky
        ovhsydney:
          ansible_host: 139.99.172.31
          ansible_user: rocky
```

Passwordless ssh login needs to be set up beween the Ansible orchestrator and each one of the target nodes (for example using ssh-copy-id).

You can limit which sites will be installed with the HOSTS variable in install_wis2_data_nodes.sh:

For example here the installation is limited to the ovhsingapour host:

For example:
```bash
$ cat install_wis2_data_nodes.sh 
#!/bin/bash

set -x

HOSTS=all
HOSTS=ovhsingapour

ansible-playbook -i inventory.yml site.yml --limit $HOSTS --start-at-task "copy directory content wis2node_data_gen"
```

### Configuration

The default configuration is avalaible in a tar file.

A link to this file is needed under ./files/common.

An then the file needs to be detared *under the subdirectory wis2_node_data_gen*:


~/files/common$ ln -s "../../../../WIS2 Data Generation/wis2node_data_gen.tar"
casa@casa-HP-EliteBook-820-G1:~/github/wis2-global-services-testing/tools/WIS2 Data Generation/

ansible-wis2-data-generators/files/common$ ls -l
total 4
lrwxrwxrwx 1 casa casa 54 Jul  3 14:19 wis2node_data_gen.tar -> '../../../../WIS2 Data Generation/wis2node_data_gen.tar'

ansible-wis2-data-generators/files/common$ cd wis2node_data_gen


~/files/common/wis2node_data_gen$ tar xvf wis2node_data_gen.tar
caddy/
caddy/Caddyfile
compose/
compose/redis-docker-compose.yml
compose/mosquitto-docker-compose.yml
compose/caddy-docker-compose.yml
compose/wis2node-docker-compose.yml
compose/traefik-docker-compose.yml
mosquitto/
mosquitto/data/
mosquitto/config/
mosquitto/config/mosquitto.conf
mosquitto/config/passwd_file
mosquitto/config/acl_file
mosquitto/log/
redis/
traefik/
traefik/dynamic/
traefik/dynamic/global.yml
traefik/acme.json
traefik/traefik.yml
wis2node/
wis2node/files/
wis2node/configuration/
wis2node/configuration/configuration.yml
wis2node/configuration/mqtt.yml
wis2node/log/
``` 

