
# Scenario 1: TSN Configuration Example
## Scenario Overview

This scenario configures the network interface to identify 4 streams.
Streams are non-VLAN and are identified based on source/destination MAC and IP.
The identified streams are classified into 3 types: Time-Aware, Non-Time-Aware, and Best Effort.
The Time-Aware and Non-Time-Aware streams are tagged with VLAN IDs and PCP values, 
while the Best Effort stream remains untagged.

| Stream Type | Count | VLAN | PCP | Queue | Features |
|---|---|---|---|---|---|
| Time-Aware (TA) | 2 | Yes | 6, 7 | q2, q3 | Routable |
| Non-Time-Aware (Non-TA) | 1 | Yes | 4 | q1 | Taggable, Routable |
| Best Effort (BE) | 1 | No | — | q0 | Non-VLAN |

## Step 1: View Configuration File

Display the TSN application configuration:

```bash
cat /etc/tch/app_config/tch_app.conf
```

Example Output:

```plaintext
root@localhost:~# cat /etc/tch/app_config/tch_app.conf

Logging:
    LogLevel: INFO
    LogDirectory: /var/log/tch
    LogFile: tch.log

General:
    Verbosity: true
    ConfigDirectory: /etc/tch/tsn_configs
    AutoCreateListeningFolder: false
    ListeningFolder:
        - /etc/tch/tsn_configs
```

## Step 2: Start Daemon

Start and verify the daemon status:

```bash
sudo tch daemon-start
sudo tch daemon-status
```

Example Output:

```plaintext

root@localhost:/home/user# tch daemon-start
Starting daemon...
✓ Daemon started successfully

root@localhost:/home/user# tch daemon-status
Checking daemon status...
Systemd service status: ✓ Service status: active

Daemon Status
========================================
Listening Folders: 1
  - /tmp/tch

✓ Daemon status retrieved successfully
========================================
```

## Step 3: Check Log Files

View the main log file:

```bash
cat /var/log/tch/tch.log
```

Example Output:

```plaintext
root@localhost:~# cat /var/log/tch/tch.log

2025-12-18 16:06:59,110 - time_config_hub.cli - INFO - Starting daemon...
2025-12-18 16:07:00,111 - tch - INFO - [daemon] Watching /etc/tch/tsn_configs
```

## Step 4: View Current TC Configuration

Display current qdisc and filter settings. Both should be empty at this stage:

```bash
tc qdisc show dev <interface>
tc filter show dev <interface> egress
```

Example Output:

```plaintext
root@localhost:~# tc qdisc show dev enp2s0          
qdisc mq 0: root
qdisc fq_codel 0: parent :4 limit 10240p flows 1024 quantum 1514 target 5ms interval 100ms memory_limit 32Mb ecn drop_batch 64
qdisc fq_codel 0: parent :3 limit 10240p flows 1024 quantum 1514 target 5ms interval 100ms memory_limit 32Mb ecn drop_batch 64
qdisc fq_codel 0: parent :2 limit 10240p flows 1024 quantum 1514 target 5ms interval 100ms memory_limit 32Mb ecn drop_batch 64
qdisc fq_codel 0: parent :1 limit 10240p flows 1024 quantum 1514 target 5ms interval 100ms memory_limit 32Mb ecn drop_batch 64
root@localhost:~# tc filter show dev enp2s0 egress
root@localhost:~#
```

## Step 5: Copy Configuration File

Copy the XML configuration to the monitored directory:

```bash
cp ~/<path-to-time-confighub>/examples/scenario_1/scenario_1-2TA_1NonTA_1BE.xml /etc/tch/tsn_configs
```

**Monitoring Features:**
- Monitors multiple folders; latest file is enrolled
- Monitors 3 file events:
    - **Create** - Enrolls configuration
    - **Modify** - Enrolls configuration
    - **Delete** - No action taken

## Step 6: Check Updated Logs

Review the log file to confirm configuration enrollment:

```bash
cat /var/log/tch/tch.log
```

Example Output:

```plaintext
root@localhost:~# cp examples/scenario_1/scenario_1-2TA_1NonTA_1BE.xml /etc/tch/tsn_configs
root@localhost:~# cat /var/log/tch/tch.log

2025-12-18 16:06:59,110 - time_config_hub.cli - INFO - Starting daemon...
2025-12-18 16:07:00,111 - tch - INFO - [daemon] Watching /etc/tch/tsn_configs
2025-12-18 16:13:11,061 - time_config_hub.cli - INFO - Checking daemon status...
2025-12-18 16:14:38,493 - time_config_hub.watch_handler - INFO - Submitting created event for processing: /etc/tch/tsn_configs/scenario_1-2TA_1NonTA_1BE.xml
2025-12-18 16:14:38,495 - time_config_hub.core - INFO - Handling file event: created for /etc/tch/tsn_configs/scenario_1-2TA_1NonTA_1BE.xml
2025-12-18 16:14:38,495 - time_config_hub.core - INFO - Applying configuration from /etc/tch/tsn_configs/scenario_1-2TA_1NonTA_1BE.xml
2025-12-18 16:14:38,497 - time_config_hub.core - INFO - 🔍 chronos-domain detected in file!
2025-12-18 16:14:38,497 - time_config_hub.core - INFO - Interfaces: ['enp2s0'], Stream IDs: ['aa-bb-cc-dd-ee-01:00-01', 'aa-bb-cc-dd-ee-01:00-02', 'aa-bb-cc-dd-ee-02:00-03', 'aa-bb-cc-dd-ee-03:00-04'], gcl: ['sched-entry S 08 1000000', 'sched-entry S 04 1000000', 'sched-entry S 02 1000000', 'sched-entry S 01 1000000']
2025-12-18 16:14:38,497 - time_config_hub.core - INFO - > Generated qdisc command:
tc qdisc replace dev enp2s0 parent root handle 100 taprio  num_tc 4 map 0 0 0 0 1 1 2 3 0 0 0 0 0 0 0 0  queues 1@0 1@1 1@2 1@3  base-time 1766045678497616407  sched-entry S 08 1000000   sched-entry S 04 1000000   sched-entry S 02 1000000   sched-entry S 01 1000000  flags 0x1 txtime-delay 200000  clockid CLOCK_TAI
2025-12-18 16:14:39,526 - time_config_hub.core - INFO - > Generated qdisc command:
tc qdisc replace dev enp2s0 parent 100:1 etf skip_sock_check offload delta 175000 clockid CLOCK_TAI
2025-12-18 16:14:40,552 - time_config_hub.core - INFO - > Generated qdisc command:
tc qdisc replace dev enp2s0 parent 100:2 etf skip_sock_check offload delta 175000 clockid CLOCK_TAI
2025-12-18 16:14:41,572 - time_config_hub.core - INFO - > Generated qdisc command:
tc qdisc replace dev enp2s0 parent 100:3 etf skip_sock_check offload delta 175000 clockid CLOCK_TAI
2025-12-18 16:14:42,593 - time_config_hub.core - INFO - > Generated qdisc command:
tc qdisc replace dev enp2s0 parent 100:4 etf skip_sock_check offload delta 175000 clockid CLOCK_TAI
...
...
...
2025-12-18 16:14:44,624 - time_config_hub.core - INFO - ----------------------------------------
2025-12-18 16:14:44,624 - time_config_hub.core - INFO - qdisc configuration applied successfully: /etc/tch/tsn_configs/scenario_1-2TA_1NonTA_1BE.xml
2025-12-18 16:14:44,624 - time_config_hub.core - INFO -
=== VLAN-Tagged & Time-Aware Talker Streams ===
2025-12-18 16:14:44,624 - time_config_hub.core - INFO -
Stream ID: aa-bb-cc-dd-ee-01:00-01
2025-12-18 16:14:44,624 - time_config_hub.core - INFO -   IF: enp2s0, MAC: AA:BB:CC:DD:EE:01, SrcMAC: AA:BB:CC:DD:EE:01, DstMAC: 01:00:5E:7F:01:01, SrcIP: 192.168.1.10, DstIP: 239.255.1.1, Port: 5001, VLAN_Tag: True, VLAN_ID: 100, PCP: 7, TimeAware: True, Offset: 1, Earliest: None, Latest: None
2025-12-18 16:14:44,624 - time_config_hub.core - INFO -
Stream ID: aa-bb-cc-dd-ee-01:00-02
2025-12-18 16:14:44,624 - time_config_hub.core - INFO -   IF: enp2s0, MAC: AA:BB:CC:DD:EE:01, SrcMAC: AA:BB:CC:DD:EE:01, DstMAC: 01:00:5E:7F:01:02, SrcIP: 192.168.1.10, DstIP: 239.255.1.2, Port: 5002, VLAN_Tag: True, VLAN_ID: 200, PCP: 6, TimeAware: True, Offset: 1000000, Earliest: None, Latest: None
2025-12-18 16:14:44,626 - time_config_hub.core - INFO -
=== Generated smart tc filter [TIME-AWARE] commands ===
2025-12-18 16:14:44,626 - time_config_hub.core - INFO - tc qdisc add dev enp2s0 clsact
2025-12-18 16:14:45,649 - time_config_hub.core - INFO - tc filter add dev enp2s0 egress protocol ip flower src_mac AA:BB:CC:DD:EE:01 dst_mac 01:00:5E:7F:01:01 src_ip 192.168.1.10 dst_ip 239.255.1.1 action vlan push id 100 protocol 802.1Q priority 7 pipe action skbedit priority 7
2025-12-18 16:14:46,692 - time_config_hub.core - INFO - tc filter add dev enp2s0 egress protocol ip flower src_mac AA:BB:CC:DD:EE:01 dst_mac 01:00:5E:7F:01:02 src_ip 192.168.1.10 dst_ip 239.255.1.2 action vlan push id 200 protocol 802.1Q priority 6 pipe action skbedit priority 6
2025-12-18 16:14:47,703 - time_config_hub.core - INFO -
=== Generated smart tc filter [NON-TIME-AWARE] commands ===
2025-12-18 16:14:47,703 - time_config_hub.core - INFO - tc filter add dev enp2s0 egress protocol ip flower src_mac AA:BB:CC:DD:EE:02 dst_mac 01:00:5E:7F:01:03 src_ip 192.168.1.20 dst_ip 239.255.1.3 action vlan push id 300 protocol 802.1Q priority 4 pipe action skbedit priority 4
...
...
...
2025-12-18 16:14:49,724 - time_config_hub.core - INFO - ----------------------------------------
2025-12-18 16:14:49,724 - time_config_hub.core - INFO - tc filter configuration applied successfully: /etc/tch/tsn_configs/scenario_1-2TA_1NonTA_1BE.xml
2025-12-18 16:14:49,724 - time_config_hub.core - INFO - Configuration applied successfully from /etc/tch/tsn_configs/scenario_1-2TA_1NonTA_1BE.xml
```

## Step 7: Verify TC Configuration

Display the enrolled configuration:

```bash
tc qdisc show dev <interface>
tc filter show dev <interface> egress
```

Example Output:

```plaintext
root@localhost:~# tc qdisc show dev enp2s0
qdisc taprio 100: root refcnt 5 tc 4 map 0 0 0 0 1 1 2 3 0 0 0 0 0 0 0 0
queues offset 0 count 1 offset 1 count 1 offset 2 count 1 offset 3 count 1
clockid TAI flags 0x1 txtime delay 200000       base-time 1766045678497616407 cycle-time 4000000 cycle-time-extension 0
        index 0 cmd S gatemask 0x8 interval 1000000
        index 1 cmd S gatemask 0x4 interval 1000000
        index 2 cmd S gatemask 0x2 interval 1000000
        index 3 cmd S gatemask 0x1 interval 1000000
max-sdu 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
fp E E E E E E E E E E E E E E E E

qdisc etf 8001: parent 100:1 clockid TAI delta 175000 offload on deadline_mode off skip_sock_check on
qdisc etf 8003: parent 100:3 clockid TAI delta 175000 offload on deadline_mode off skip_sock_check on
qdisc etf 8002: parent 100:2 clockid TAI delta 175000 offload on deadline_mode off skip_sock_check on
qdisc etf 8004: parent 100:4 clockid TAI delta 175000 offload on deadline_mode off skip_sock_check on
qdisc clsact ffff: parent ffff:fff1

root@localhost:~# tc filter show dev enp2s0 egress
filter protocol ip pref 49150 flower chain 0
filter protocol ip pref 49150 flower chain 0 handle 0x1
  dst_mac 01:00:5e:7f:01:03
  src_mac aa:bb:cc:dd:ee:02
  eth_type ipv4
  dst_ip 239.255.1.3
  src_ip 192.168.1.20
  not_in_hw
        action order 1: vlan  push id 300 protocol 802.1Q priority 4 pipe
         index 3 ref 1 bind 1

        action order 2: skbedit  priority :4 pipe
         index 3 ref 1 bind 1

filter protocol ip pref 49151 flower chain 0
filter protocol ip pref 49151 flower chain 0 handle 0x1
  dst_mac 01:00:5e:7f:01:02
  src_mac aa:bb:cc:dd:ee:01
  eth_type ipv4
  dst_ip 239.255.1.2
  src_ip 192.168.1.10
  not_in_hw
        action order 1: vlan  push id 200 protocol 802.1Q priority 6 pipe
         index 2 ref 1 bind 1

        action order 2: skbedit  priority :6 pipe
         index 2 ref 1 bind 1

filter protocol ip pref 49152 flower chain 0
filter protocol ip pref 49152 flower chain 0 handle 0x1
  dst_mac 01:00:5e:7f:01:01
  src_mac aa:bb:cc:dd:ee:01
  eth_type ipv4
  dst_ip 239.255.1.1
  src_ip 192.168.1.10
  not_in_hw
        action order 1: vlan  push id 100 protocol 802.1Q priority 7 pipe
         index 1 ref 1 bind 1

        action order 2: skbedit  priority :7 pipe
         index 1 ref 1 bind 1
```

