import argparse
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI

def run_topology(bw, start_server):
    # Initialize Mininet with the specified classes[cite: 14]
    net = Mininet(switch=OVSKernelSwitch, link=TCLink, controller=RemoteController)

    # Add the Ryu controller on 127.0.0.1 port 6653[cite: 4, 15]
    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)

    # Add the switch with OpenFlow 1.3
    s1 = net.addSwitch('s1', protocols='OpenFlow13')

    # Add hosts h1 to h6 with specific IPs[cite: 4, 15]
    h1 = net.addHost('h1', ip='10.0.0.1')
    h2 = net.addHost('h2', ip='10.0.0.2')
    h3 = net.addHost('h3', ip='10.0.0.3')
    h4 = net.addHost('h4', ip='10.0.0.4')
    h5 = net.addHost('h5', ip='10.0.0.5')
    h6 = net.addHost('h6', ip='10.0.0.6')

    # Add links in exact order so host N is on port N of the switch
    # TCLink uses the bw argument to enforce the speed limit
    net.addLink(h1, s1, bw=bw) # s1-eth1
    net.addLink(h2, s1, bw=bw) # s1-eth2
    net.addLink(h3, s1, bw=bw) # s1-eth3
    net.addLink(h4, s1, bw=bw) # s1-eth4
    net.addLink(h5, s1, bw=bw) # s1-eth5
    net.addLink(h6, s1, bw=bw) # s1-eth6

    net.start()

    # Optional flag to start the server automatically on h1
    if start_server:
        print("*** Starting file server on h1...")
        h1.cmd('python3 server/server.py &')

    # Start the Mininet command line
    CLI(net)

    # Clean up after exiting the CLI
    net.stop()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Mininet Topology")
    parser.add_argument('--bw', type=int, default=10, help="Link bandwidth in Mbps (0 for unlimited)")
    parser.add_argument('--server', action='store_true', help="Start the file server on h1")
    args = parser.parse_args()
    
    run_topology(args.bw, args.server)
