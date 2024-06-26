# Tool to generate (a lot of) WIS2 Notification Messages

The code in this repository is to provide the required tools to assess the performance of the Global Broker. 
The docker-compose file deploys 4 containers: two for message generation, one for mosquitto and one for traefik.

## What does it do ?

1. Listen to a central MQTT Broker where instructions to publish messages can be sent
2. Creates the number of notification messages as instructed
3. Each golfvert/benchmarkwis2gb container "emulates" 20 WIS2 Nodes (only for Notification Message generation). Each WIS2 Node as a centre-id io-wis2dev-[number]-test


## How to use it ?

Download 
- docker-compose.yaml

and edit, for each of the two golfvert/benchmarkwis2gb container :

```
      environment:
        - MQTT_CONFIG_BROKER=
        - MQTT_CONFIG_USERNAME=
        - MQTT_CONFIG_PASSWORD=
        - MQTT_CONFIG_TOPIC=config/#
        - CENTRE_ID=100
        - MQTT_PUB_BROKER=mqtt://mosquitto
        - MQTT_PUB_USERNAME=mqtt
        - MQTT_PUB_PASSWORD=****
        - MQTT_PUB_BROKERVERSION=5
        - MQTT_PUB_QOS=1
 ```

MQTT_CONFIG_BROKER/USERNAME/PASSWORD/TOPIC must be identical on all servers participating to the benchmark. 
Typically, a free instance of HiveMQ/EMQX running in the cloud can be used.

The CENTRE_ID must be changed for each instance of the deployed docker container.
By convention, the lowest usable value is 100. Then, the other WIS2 Nodes within the same container will be 101, 102,... 119.
The second instance of the container should have `CENTRE_ID=120` and so on.

The `mosquitto` container deployed and the attached configuration file is then used to publish messages (using mqtt username) and can be subscribed to (using everyone/everyone).

The tested Global Broker should then subscribe to all WIS2 Nodes message generation using the CENTRE_ID io-wis2dev-100-test, -101-,... 
In the envisaged test scenario, 200 WIS2 Nodes should be configured. So, up to io-wis2dev-299-test. Those 200 WIS2 Node will be distributed onto 5 VMs for performance reasons.
