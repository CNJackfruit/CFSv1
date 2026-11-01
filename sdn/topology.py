#!/usr/bin/env python3
"""Mininet topology: one switch s1, server h1 (10.0.0.1), clients h2..h6.

Links are added in order h1..h6, so host N sits on switch port N.

Usage (from the project root, Ryu already running):
    sudo python3 sdn/topology.py                # 10 Mbps links
    sudo python3 sdn/topology.py --bw 0         # unlimited links
    sudo python3 sdn/topology.py --server       # also start the file server on h1
"""
import argparse
import os

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM_HOSTS = 6  # h1 = server, h2..h6 = clients


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bw", type=float, default=10,
                    help="link bandwidth in Mbps (0 = unlimited), default 10")
    ap.add_argument("--server", action="store_true",
                    help="start the file server on h1")
    ap.add_argument("--controller-ip", default="127.0.0.1")
    ap.add_argument("--controller-port", type=int, default=6653)
    args = ap.parse_args()

    setLogLevel("info")
    net = Mininet(controller=None, switch=OVSKernelSwitch, link=TCLink,
                  autoSetMacs=True)
    net.addController("c0", controller=RemoteController,
                      ip=args.controller_ip, port=args.controller_port)
    s1 = net.addSwitch("s1", protocols="OpenFlow13")

    # Add links in order so that host N is on port N.
    for i in range(1, NUM_HOSTS + 1):
        h = net.addHost("h%d" % i, ip="10.0.0.%d/24" % i)
        if args.bw > 0:
            net.addLink(h, s1, bw=args.bw)
        else:
            net.addLink(h, s1)

    net.start()

    if args.server:
        h1 = net.get("h1")
        os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
        h1.cmd("cd %s && python3 server/server.py --port 9000 "
               "--storage server/storage > results/server.log 2>&1 &" % ROOT)
        info("*** File server started on h1 (log: results/server.log)\n")

    info("*** Host -> switch port: h1=1 h2=2 h3=3 h4=4 h5=5 h6=6\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    main()
