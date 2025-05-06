# Tool to generate (a lot of) WIS2 Notification Messages

The code in this repository is to provide the required tools to assess the performance of the Global Broker. 
The docker-compose file deploys 4 containers: two for message generation, one for mosquitto and one for traefik.

## What does it do ?

1. Listen to a central MQTT Broker where instructions to publish messages can be sent
2. Creates the number of notification messages as instructed
3. Each golfvert/benchmarkwis2gb container "emulates" 20 WIS2 Nodes (only for Notification Message generation). Each WIS2 Node as a centre-id io-wis2dev-[number]-test


## How to deploy it ?

### Manually

Download :
- docker-compose.yml

and edit, for each of the two golfvert/benchmarkwis2gb container :

```
      environment:
        - MQTT_CONFIG_BROKER=
        - MQTT_CONFIG_USERNAME=
        - MQTT_CONFIG_PASSWORD=
        - MQTT_CONFIG_TOPIC=config/#
        - CENTRE_ID=100
 ```

MQTT_CONFIG_BROKER/USERNAME/PASSWORD/TOPIC must be identical on all servers participating to the benchmark. 
Typically, a free instance of HiveMQ/EMQX running in the cloud can be used.

The CENTRE_ID must be changed for each instance of the deployed docker container.
By convention, the lowest usable value is 100. Then, the other WIS2 Nodes within the same container will be 101, 102,... 119.
The second instance of the container should have `CENTRE_ID=120` and so on.

The `mosquitto` container deployed and the attached configuration file is then used to publish messages (using mqtt username) and can be subscribed to (using everyone/everyone).

The tested Global Broker should then subscribe to all WIS2 Nodes message generation using the CENTRE_ID io-wis2dev-100-test, -101-,... 
In the envisaged test scenario, 200 WIS2 Nodes should be configured. So, up to io-wis2dev-299-test. Those 200 WIS2 Node will be distributed onto 5 VMs for performance reasons.

### Using Ansible

Download : 
- inventory, ansible-playbook,... The playbook works with managed nodes running Rocky (or equivalent) Linux.
- the docker-compose template

1. Prepare the ansible configuration on the control node (this will need the docker tools) and the managed nodes (ssh access with password-less sudo, for example).
2. With the IP addresses (or DNS names) of the managed nodes, update the inventory accordingly. On each managed node, two docker containers for the message generation will be deployed. The values for centre_id must be adapted accordingly. Typically, the 1st VM will have 100 to 119 on the 1st container, the 2nd VM will have 120 to 139. And so on.
3. Modify the MQTT_CONFIG_BROKER/USERNAME/PASSWORD/TOPIC as explained above

## How to use it ?

By publishing instructions on the MQTT_CONFIG_BROKER, some or all of the WIS2 Nodes will then generate messages compliant with WIS2 Notification Message format. 
No associated data will be created. The purpose of the tool being _only_ to create a large number of Notification Messages that the Global Brokers should handle properly.

The following JSON message is an example showing how to trigger the WIS2 Notification Message generation by the WIS2 Nodes:

```
{
  "centreid_min": 101,
  "centreid_max": 107,
  "action":
    {
      "publish":
      { "delay": 10,
        "number": 1000
      }
    } 
}
```

Each WIS2 Node has a centre_id number. The above example will instruct WIS2 Node whose centre_id are above 101 and below 107 (both included) to send 1000 messages with a delay of 10ms between each message.

By adjusting centreid_min and centreid_max, the delay between messages and the number of messages to send, it is possible to assess the performance of the Global Broker.
Each generated message will have its own `id`.
