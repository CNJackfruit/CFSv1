# CFSv1 — Concurrent File Sharing with TLS and SDN

A multi-client file-sharing system built using **Python, TCP/TLS, Mininet, Open vSwitch, and the Ryu SDN controller**.

CFSv1 enables multiple clients to upload and download files concurrently while a Software-Defined Networking (SDN) controller manages network access policies, monitors bandwidth, and dynamically blocks clients after repeated authentication failures.

## Overview

Traditional file-sharing applications handle data transfer at the application layer. CFSv1 extends this by integrating an SDN-controlled network that can enforce access policies independently of the file server.

The project combines three main components:

- **Concurrent file sharing:** A multithreaded TCP/TLS server supporting user authentication, file uploads, downloads, and file integrity verification.
- **SDN-based network control:** A Ryu OpenFlow controller that manages client access through configurable policies and monitors network bandwidth.
- **Dynamic security response:** Failed-login events from the application are communicated to the SDN controller, which temporarily blocks the offending client at the network level.

## Key Features

### File-sharing system
- Multiple clients can connect and transfer files concurrently.
- User registration and login.
- Authenticated file listing, uploading, and downloading.
- SHA-256 checksums for file integrity verification.
- File ownership and metadata management.
- Thread-safe file operations and metadata updates.
- TLS-encrypted client-server communication.

### SDN integration
- Mininet-based network topology with one Open vSwitch.
- Ryu controller using OpenFlow 1.3.
- IP-based allow/deny policies for file-server traffic.
- Live policy updates without restarting the controller.
- Periodic bandwidth monitoring and CSV logging.
- Network-level blocking of clients after repeated failed logins.
- Automatic expiration of temporary blocking rules.

### Testing and analysis
- Concurrent transfer testing using multiple threads.
- Support for upload and download experiments.
- Tests can be distributed across different Mininet hosts.
- Per-transfer timing, throughput, and success/failure logging.
- Aggregate throughput analysis across experiment runs.

---

## Architecture

```text
                         +---------------------------+
                         |       Ryu Controller      |
                         |                           |
                         |  - OpenFlow 1.3           |
                         |  - Access policy engine   |
                         |  - Bandwidth monitoring   |
                         |  - Dynamic auto-block     |
                         +-------------+-------------+
                                       |
                                  OpenFlow 1.3
                                       |
                                       v
       +---------------------------------------------------+
       |                  Open vSwitch                     |
       |                       s1                          |
       +---------------------------------------------------+
           |          |          |          |          |
           |          |          |          |          |
          h1         h2         h3         h4         h5/h6
        Server     Client     Client     Client      Clients
       10.0.0.1  10.0.0.2  10.0.0.3  10.0.0.4  10.0.0.5-6
           |
           |
     TCP/TLS :9000
           |
           v
    File-sharing service
    - Authentication
    - Upload / Download
    - Metadata management
    - SHA-256 verification
    - Failed-login detection
           |
           | Failed-login events
           v
      sdn/events.jsonl
           |
           +----------------------> Ryu Controller
```

### Network topology

The Mininet topology consists of one server, five clients, and one Open vSwitch.

| Host | IP address | Role |
|---|---|---|
| h1 | 10.0.0.1 | File server |
| h2 | 10.0.0.2 | Client |
| h3 | 10.0.0.3 | Client |
| h4 | 10.0.0.4 | Client |
| h5 | 10.0.0.5 | Client |
| h6 | 10.0.0.6 | Client |

The default topology uses 10 Mbps links. The default SDN policy denies h4 while allowing the other clients.

### Communication

| Component | Protocol | Port |
|---|---|---|
| File server and clients | TCP over TLS | 9000 |
| Ryu controller and switch | OpenFlow 1.3 over TCP | 6653 |

The file server handles application-level operations, while the SDN controller independently controls network-level access to the server.

---

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Server, clients, controller, and testing tools |
| TCP sockets | Client-server communication |
| TLS / SSL | Encrypted file transfers |
| SHA-256 | File integrity verification and password hashing |
| Mininet | Virtual network emulation |
| Open vSwitch | SDN-enabled virtual switch |
| Ryu | SDN controller |
| OpenFlow 1.3 | Controller-switch communication |
| JSON | Application protocol, configuration, and metadata |
| CSV | Transfer and bandwidth measurements |

The file server, clients, and test scripts use Python's standard library. Ryu and its dependencies are installed separately in a virtual environment.

---

## Getting Started

### Prerequisites

- Ubuntu Linux (recommended: Ubuntu 22.04).
- Python 3.8 or newer for the server, clients, and tests.
- Python 3.9 for the Ryu virtual environment.
- Mininet and Open vSwitch.
- Git and OpenSSL.

**Note:** Mininet requires a Linux environment. Windows and macOS users can use an Ubuntu virtual machine.

### 1. Clone the repository

```bash
git clone https://github.com/CNJackfruit/CFSv1.git
cd CFSv1
```

Run subsequent commands from the project root unless stated otherwise.

### 2. Install Mininet and Open vSwitch

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch
```

Verify the installation:

```bash
sudo mn --version
```

### 3. Set up the Ryu environment

Ryu 4.34 requires an older Python packaging toolchain. The following installation sequence avoids common build issues.

```bash
python3.9 -m venv ryu-env
source ryu-env/bin/activate

pip install --upgrade pip
pip install eventlet==0.30.2
pip install "setuptools==57.5.0" wheel pbr
pip install --no-build-isolation ryu==4.34
```

Verify:

```bash
ryu-manager --version
```

Expected version:

```text
ryu-manager 4.34
```

If Python 3.9 is not available through your distribution, you can use [uv](https://docs.astral.sh/uv/) to create the environment:

```bash
uv venv --seed --python 3.9 ryu-env
```

If you already have a working Ryu 4.34 environment, you can skip this step.

### 4. Generate TLS certificates

The server expects `server.crt` and `server.key` in the project root.

Generate a self-signed certificate:

```bash
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout server.key \
  -out server.crt \
  -days 365 \
  -subj "/CN=localhost"
```

These certificate files are generated locally and are not committed to the repository.

### 5. Generate test files

The test files are generated locally rather than stored in Git.

Generate all supported file sizes:

```bash
python3 tests/make_files.py
```

Generate only a 5 MB file:

```bash
python3 tests/make_files.py --sizes 5
```

Generated files are placed in `tests/files/` by default.

### 6. User accounts

The repository includes sample accounts:

| Username | Password |
|---|---|
| vamshi | vamshi |
| user0 | user0 |
| user1 | user1 |
| user2 | user2 |
| ... | ... |
| user49 | user49 |

The concurrent test tool uses `user1` through `user5`.

You can register additional users through the interactive client.

---

## Running the Full SDN Demonstration

The full demonstration requires two terminals.

Both terminals should be opened in the project root.

### Terminal 1 — Start the Ryu controller

First, clean up any previous Mininet environment:

```bash
sudo mn -c
```

Activate the Ryu environment:

```bash
source ryu-env/bin/activate
```

Start the controller:

```bash
ryu-manager sdn/controller.py
```

The controller should load `sdn/policy.json` and wait for the Open vSwitch connection.

Once Mininet starts, you should see a switch connection message and the installed policy rules.

**Important:** Run `sudo mn -c` before starting Ryu. It can also terminate an already-running controller.

### Terminal 2 — Start Mininet and the file server

```bash
sudo python3 sdn/topology.py --server
```

This creates the virtual network and starts the file server on h1.

The server log is written to:

```text
results/server.log
```

Wait for the `mininet>` prompt.

### 1. Check network connectivity

At the Mininet prompt:

```text
pingall
```

The default SDN policy controls TCP traffic to the file-server port. Ping traffic remains available.

### 2. Test concurrent uploads

Run four simultaneous uploads from h2:

```text
h2 python3 tests/concurrent_tests.py --port 9000 10.0.0.1 4 upload tests/files/5MB.bin run_5mb_up
```

Each thread establishes its own connection and authenticates as a separate user.

### 3. Verify uploaded files

```text
h2 python3 client/client2.py --host 10.0.0.1 --port 9000 --user vamshi --password vamshi list
```

### 4. Test concurrent downloads

```text
h2 python3 tests/concurrent_tests.py --port 9000 10.0.0.1 4 download tests/files/5MB.bin run_5mb_dl
```

The test tool ensures the requested file exists before the timed download experiment.

Every downloaded file is verified using SHA-256.

A successful run produces output similar to:

```text
[run_5mb_up] upload threads=4 ok=4 failed=0 wall=19.726s min=19.021s avg=19.241s max=19.704s

[run_5mb_dl] download threads=4 ok=4 failed=0 wall=20.117s min=19.567s avg=19.794s max=20.110s
```

`failed=0` indicates that all transfers completed successfully and passed integrity verification.

### 5. Test SDN access control

The default policy denies h4 (`10.0.0.4`).

Try accessing the file server from h4:

```text
h4 python3 client/client2.py --host 10.0.0.1 --port 9000 --user vamshi --password vamshi list
```

The connection should time out because the switch drops the traffic.

### 6. Test live policy updates

While the controller is running, edit:

```text
sdn/policy.json
```

For example, add a deny rule for h2:

```json
{
  "id": 0,
  "action": "deny",
  "src_ip": "10.0.0.2"
}
```

The controller checks the policy file periodically and reloads valid changes without requiring a restart.

The updated rules should take effect within approximately two seconds.

Remove the deny rule to restore access.

To inspect the installed OpenFlow rules:

```text
sh ovs-ofctl -O OpenFlow13 dump-flows s1
```

### 7. Test dynamic auto-blocking

The application tracks failed login attempts by client IP address.

After three failed login attempts, the server writes an event to `sdn/events.jsonl`. The controller reads this event and installs temporary OpenFlow drop rules for the offending client.

For a longer demonstration window, start the controller with:

```bash
BLOCK_SECONDS=120 ryu-manager sdn/controller.py
```

Use h6, which is allowed by the default policy.

Run the following command three times from the Mininet prompt:

```text
h6 python3 client/client2.py --host 10.0.0.1 --port 9000 --user user1 --password wrong list
```

After the third failed attempt, the server reports:

```text
Too many failed login attempts
```

The controller should log an event and an auto-block message similar to:

```text
EVENT from server: failed_logins ip=10.0.0.6 count=3
AUTO-BLOCK 10.0.0.6 for 120 s
```

Inspect the switch rules:

```text
sh ovs-ofctl -O OpenFlow13 dump-flows s1 | grep 2000
```

The controller installs high-priority drop rules with a temporary timeout.

During the block:

- h6 cannot access the file server.
- h6 can still ping the server.
- Other allowed clients can still access the server.

When the timeout expires, the switch automatically removes the blocking rules and the controller reports that access has been restored.

### 8. Shut down

Exit Mininet:

```text
exit
```

Stop the Ryu controller using `Ctrl+C`.

Clean up the Mininet environment:

```bash
sudo mn -c
```

---

## Running Without Mininet

The file-sharing application can also be tested independently of the SDN layer.

Start the server from the project root:

```bash
python3 server/server.py --port 9000
```

In another terminal, list files:

```bash
python3 client/client2.py \
  --host 127.0.0.1 --port 9000 \
  --user vamshi --password vamshi list
```

Upload a file:

```bash
python3 client/client2.py \
  --host 127.0.0.1 --port 9000 \
  --user vamshi --password vamshi \
  upload tests/files/1MB.bin
```

Download a file:

```bash
python3 client/client2.py \
  --host 127.0.0.1 --port 9000 \
  --user vamshi --password vamshi \
  download 1MB.bin --dest downloads
```

Run concurrent uploads:

```bash
python3 tests/concurrent_tests.py \
  --port 9000 127.0.0.1 4 upload \
  tests/files/5MB.bin local_up
```

Run concurrent downloads:

```bash
python3 tests/concurrent_tests.py \
  --port 9000 127.0.0.1 4 download \
  tests/files/5MB.bin local_dl
```

The application-level failed-login events also work in localhost mode. However, the controller intentionally ignores loopback addresses, so network-level auto-blocking must be demonstrated through Mininet.

---

## SDN Policy Configuration

The controller reads its access-control rules from:

```text
sdn/policy.json
```

Default configuration:

```json
{
  "server_ip": "10.0.0.1",
  "server_port": 9000,
  "default_action": "deny",
  "rules": [
    {
      "id": 1,
      "action": "deny",
      "src_ip": "10.0.0.4"
    },
    {
      "id": 2,
      "action": "allow",
      "src_ip": "*"
    }
  ]
}
```

### Policy behaviour

- Rules are evaluated from top to bottom.
- The first matching rule determines the action.
- `*` matches every client IP.
- If no rule matches, `default_action` is applied.
- Only TCP traffic to and from the configured file-server port is controlled.
- The controller periodically checks for policy-file modifications.
- Invalid policy files are rejected, leaving the previous valid policy active.

Each access rule is translated into OpenFlow rules for both client-to-server and server-to-client traffic.

The controller also installs a baseline `NORMAL` flow so that other network traffic, including ARP and ping, continues to work.

### Bandwidth monitoring

The Ryu controller periodically requests port statistics from the switch.

It calculates and records per-port receive and transmit throughput.

The output is stored in:

```text
sdn/bandwidth.csv
```

The CSV format is:

```text
time,switch,port,host,rx_mbps,tx_mbps
```

The measurements help identify how network traffic is distributed among clients and the server.

---

## Concurrent Testing and Performance Analysis

The project includes tools for evaluating how the file-sharing system behaves under simultaneous client transfers.

### Concurrent test tool

```bash
python3 tests/concurrent_tests.py [--port 9000] HOST THREADS {upload|download} FILE TAG
```

Each test thread:

1. Establishes an independent TCP/TLS connection.
2. Logs in using a separate test account.
3. Waits at a synchronization barrier.
4. Performs an upload or download.
5. Records transfer duration, throughput, and success status.

Uploads use unique filenames. Downloads use separate temporary directories to avoid conflicts.

### Analyse experiment results

```bash
python3 tests/analyse.py --csv results/transfers.csv
```

Filter experiments by tag prefix:

```bash
python3 tests/analyse.py --tag-prefix E2_
```

The analysis reports:

- Number of transfers.
- Failed transfers.
- Minimum, average, and maximum transfer duration.
- Average and slowest-client throughput.
- Aggregate throughput across the experiment.

Use a different tag for every experiment run to avoid merging results unintentionally.

### Sample performance results

The following measurements were obtained in the Mininet environment using 10 Mbps links and 5 MB downloads.

| Simultaneous clients | Failed transfers | Average time per transfer | Average Mbps per client | Aggregate Mbps |
|---:|---:|---:|---:|---:|
| 1 | 0 | 4.73 s | 8.86 | 8.86 |
| 2 | 0 | 9.19 s | 4.56 | 8.94 |
| 5 | 0 | 22.94 s | 1.83 | 8.94 |
| 10 | 0 | 41.06 s | 1.04 | 7.51 |
| 20 | 0 | 89.03 s | 0.47 | 9.21 |

The aggregate throughput remains close to the configured 10 Mbps link capacity, with some variation due to TCP/TLS overhead and experiment timing.

As the number of simultaneous clients increases, the available bandwidth is shared among them.

All transfers in these runs completed successfully and passed SHA-256 verification.

**Note:** These are measurements from an emulated Mininet environment, not real-world network benchmarks.

---

## Project Structure

```text
CFSv1/
│
├── server/
│   ├── server.py
│   ├── auth.py
│   ├── metadata.py
│   ├── utils.py
│   └── users.json
│
├── client/
│   ├── client.py
│   ├── client2.py
│   └── utils.py
│
├── sdn/
│   ├── controller.py
│   ├── topology.py
│   └── policy.json
│
├── tests/
│   ├── concurrent_tests.py
│   ├── make_files.py
│   └── analyse.py
│
├── database/
│   └── .gitkeep
│
├── results/
│
├── users.json
├── output.png
├── output2.png
└── README.md
```

### Important generated files

The following files and directories are created locally during execution:

| File / Directory | Purpose |
|---|---|
| `server.crt`, `server.key` | TLS certificate and private key |
| `metadata.json` | File registry and metadata |
| `storage/` | Uploaded file storage |
| `tests/files/` | Generated test files |
| `sdn/events.jsonl` | Application events consumed by the controller |
| `sdn/bandwidth.csv` | Network bandwidth measurements |
| `results/transfers.csv` | Concurrent transfer measurements |
| `results/server.log` | File-server logs |
| `ryu-env/` | Ryu Python virtual environment |

Generated files, private keys, and local environments should not be committed to the repository.

---

## Protocol Overview

The application uses a simple JSON-based protocol over TCP/TLS.

Each control message is a JSON object terminated by a newline. File contents are transferred as raw bytes after the relevant message header.

### Client commands

| Command | Description |
|---|---|
| `LOGIN` | Authenticate a user |
| `REGISTER` | Register a new user |
| `LIST` | Retrieve available file metadata |
| `UPLOAD` | Upload a file |
| `DOWNLOAD` | Download a file |
| `QUIT` | Close the session |

Example login message:

```json
{
  "cmd": "LOGIN",
  "username": "vamshi",
  "password": "vamshi"
}
```

Example upload header:

```json
{
  "cmd": "UPLOAD",
  "name": "report.pdf",
  "size": 1048576,
  "sha256": "<64 hex characters>"
}
```

The receiver reads the specified number of bytes rather than relying on TCP packet boundaries. This is important because TCP provides a continuous byte stream, not individual application messages.

The implementation uses `ProtocolReader` to handle newline-delimited messages and exact-length byte reads.

### File integrity

For uploads, the client calculates a SHA-256 checksum and sends it with the file metadata.

The server verifies the received file before accepting it into storage.

For downloads, the client verifies the checksum received from the server. A file that fails verification is discarded.

---

## Configuration Reference

### File server

```bash
python3 server/server.py --port 9000
```

| Option | Default | Description |
|---|---|---|
| `--port` | `9000` | TCP port used by the file server |
| `--storage` | `database` | Storage directory name |

The server's storage directory is created inside the project root.

The Mininet topology starts the server using `--storage server/storage`, which results in uploaded files being stored in the project's `storage/` directory.

The failed-login threshold is configured through `FAIL_LIMIT` in `server/server.py` (default: 3).

### Mininet topology

```bash
sudo python3 sdn/topology.py --server
```

| Option | Default | Description |
|---|---:|---|
| `--bw` | `10` | Link bandwidth in Mbps; `0` means unlimited |
| `--server` | Disabled | Start the file server on h1 |
| `--controller-ip` | `127.0.0.1` | Ryu controller address |
| `--controller-port` | `6653` | Ryu controller port |

### Ryu controller

| Environment variable | Default | Description |
|---|---|---|
| `POLICY_FILE` | `sdn/policy.json` | Access-control policy file |
| `BW_CSV` | `sdn/bandwidth.csv` | Bandwidth measurement output |
| `EVENTS_FILE` | `sdn/events.jsonl` | Application event file |
| `BLOCK_SECONDS` | `30` | Duration of temporary auto-blocking |

If `EVENTS_FILE` is changed, configure the server and controller to use the same path.

---

## Troubleshooting

| Problem | Possible solution |
|---|---|
| Ryu installation fails with `get_script_args` | Follow the pinned setuptools and Ryu installation sequence in the setup section. |
| Ryu reports version `2.2` | Reinstall using `pbr` and explicitly pin `ryu==4.34`. |
| Connection refused on port 9000 | Check whether the server is running and whether the TLS certificate files exist. |
| Client connection times out | Check the SDN policy, controller logs, and installed switch flows. |
| `Unknown command: mininet>` | Do not include the `mininet>` prompt when copying commands. |
| Controller stops after `sudo mn -c` | Start the controller after Mininet cleanup. |
| Address already in use | Check for leftover server or controller processes. |
| Permission denied on generated files | Files may have been created using `sudo`. Run `sudo chown -R "$USER": .` from the project root. |
| No auto-block event appears | Check `sdn/events.jsonl` and ensure the controller started before the event was generated. |
| Auto-block expires too quickly | Set `BLOCK_SECONDS=120` when starting the controller for demonstrations. |
| No flows appear in Mininet | Run `sh ovs-ofctl -O OpenFlow13 dump-flows s1` from the Mininet prompt. |

---

## Current Limitations and Security Considerations

CFSv1 is an experimental project demonstrating concurrent file sharing and SDN-based network control. It is not intended to be deployed as a production file-sharing service.

Known limitations include:

- **Password storage:** Passwords are currently stored as unsalted SHA-256 hashes. A production implementation should use a dedicated password-hashing algorithm such as Argon2id, scrypt, or PBKDF2 with unique salts.
- **TLS certificate verification:** The clients currently skip server certificate verification because the demonstration uses a self-signed certificate. Production deployments must validate server certificates.
- **IP-based access control:** Access policies and automatic blocking use source IP addresses. IP-based identity can be spoofed, and multiple users sharing an IP may be affected together.
- **Single-switch topology:** The current demonstration uses one Open vSwitch and one Ryu controller.
- **Thread-per-client model:** The server creates a separate thread for each client connection.
- **Shared event file:** The application communicates failed-login events to the controller through `sdn/events.jsonl`. This works in the local Mininet environment, but a distributed deployment would need a network-based event mechanism.
- **In-memory failed-login tracking:** Failed-login counters are lost when the server restarts.
- **Limited security triggers:** Automatic blocking currently responds to repeated failed logins. Bandwidth monitoring is observational and does not trigger automatic traffic shaping or blocking.
- **Emulated performance:** Mininet throughput measurements do not represent real-world network performance.
- **Limited file operations:** The current application supports listing, uploading, and downloading files; a delete operation is not implemented.

These limitations provide clear directions for future improvements, including stronger authentication, certificate validation, distributed event communication, more advanced SDN policies, and expanded file-management functionality.

---

## Future Improvements

Potential extensions include:

- Stronger password hashing and proper TLS certificate validation.
- More granular user and file permissions.
- Support for file deletion and additional file operations.
- Rate limiting and bandwidth-aware traffic policies.
- More advanced SDN policies based on traffic patterns.
- Persistent failed-login tracking.
- A network-based interface between the application and controller.
- Multi-switch and multi-controller topologies.
- Testing under larger client loads and more realistic network conditions.

---

## Contributors

Developed as a Computer Networks and Software-Defined Networking project.

**Repository:** [CNJackfruit/CFSv1](https://github.com/CNJackfruit/CFSv1)


