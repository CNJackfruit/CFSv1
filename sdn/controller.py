"""Ryu controller (OpenFlow 1.3) for the file-sharing project.

Features
  * baseline flow (priority 1, NORMAL) so the switch behaves like a normal L2 switch
  * policy.json -> flow rules (allow/deny by client IP for the file-server port)
  * live reload of policy.json (mtime checked every 2 s, bad file keeps old policy)
  * bandwidth monitor: port counters every 2 s -> console + bandwidth.csv

Run (from the project root):
    ryu-manager sdn/controller.py
Optional environment variables:
    POLICY_FILE   path to policy.json   (default: sdn/policy.json)
    BW_CSV        path to bandwidth.csv (default: bandwidth.csv beside controller.py)
"""
import csv
import ipaddress
import json
import os
import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (CONFIG_DISPATCHER, DEAD_DISPATCHER,
                                    MAIN_DISPATCHER, set_ev_cls)
from ryu.lib import hub
from ryu.ofproto import ofproto_v1_3

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
POLICY_PATH = os.environ.get("POLICY_FILE", os.path.join(HERE, "policy.json"))
BW_CSV_PATH = os.environ.get("BW_CSV", os.path.join(HERE, "bandwidth.csv"))

CHECK_INTERVAL = 2      # seconds: policy file check and port-stats request
BASELINE_PRIORITY = 1
DEFAULT_DENY_PRIORITY = 10
RULE_BASE_PRIORITY = 1000
PRINT_THRESHOLD_MBPS = 0.01


# ---------------------------------------------------------------------------
# Pure functions (no OpenFlow objects) - easy to test by hand
# ---------------------------------------------------------------------------
def load_policy(path):
    """Read and validate policy.json. Returns a dict or raises ValueError."""
    with open(path) as f:
        try:
            p = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError("invalid JSON: %s" % e)

    if not isinstance(p, dict):
        raise ValueError("policy must be a JSON object")
    try:
        ipaddress.ip_address(p["server_ip"])
        port = p["server_port"]
        if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
            raise ValueError("server_port must be an integer 1-65535")
        if p["default_action"] not in ("allow", "deny"):
            raise ValueError("default_action must be 'allow' or 'deny'")
        rules = p["rules"]
    except KeyError as e:
        raise ValueError("missing field %s" % e)
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")

    for r in rules:
        if not isinstance(r, dict):
            raise ValueError("each rule must be an object")
        if r.get("action") not in ("allow", "deny"):
            raise ValueError("rule %s: action must be 'allow' or 'deny'" % r.get("id"))
        src = r.get("src_ip")
        if src != "*":
            try:
                ipaddress.ip_address(src)
            except ValueError:
                raise ValueError("rule %s: bad src_ip %r" % (r.get("id"), src))
    return p


def build_flows(policy):
    """Turn a policy into a list of (priority, match_dict, 'allow'|'drop', rule_id).

    Rule at position k gets priority 1000 - k, and produces two flows:
    client -> server and server -> client.
    """
    server = policy["server_ip"]
    port = policy["server_port"]
    flows = []

    for k, rule in enumerate(policy["rules"]):
        prio = RULE_BASE_PRIORITY - k
        act = "allow" if rule["action"] == "allow" else "drop"
        rid = rule.get("id", k + 1)
        src = rule["src_ip"]

        fwd = {"eth_type": 0x0800, "ip_proto": 6,
               "ipv4_dst": server, "tcp_dst": port}
        rev = {"eth_type": 0x0800, "ip_proto": 6,
               "ipv4_src": server, "tcp_src": port}
        if src != "*":
            fwd["ipv4_src"] = src
            rev["ipv4_dst"] = src
        flows.append((prio, fwd, act, rid))
        flows.append((prio, rev, act, rid))

    if policy["default_action"] == "deny":
        flows.append((DEFAULT_DENY_PRIORITY,
                      {"eth_type": 0x0800, "ip_proto": 6,
                       "ipv4_dst": server, "tcp_dst": port}, "drop", "default"))
        flows.append((DEFAULT_DENY_PRIORITY,
                      {"eth_type": 0x0800, "ip_proto": 6,
                       "ipv4_src": server, "tcp_src": port}, "drop", "default"))
    return flows


# Safe fallback if policy.json is broken at start-up.
FALLBACK_POLICY = {"server_ip": "10.0.0.1", "server_port": 9000,
                   "default_action": "deny", "rules": []}


# ---------------------------------------------------------------------------
# Ryu application
# ---------------------------------------------------------------------------
class FileShareController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(FileShareController, self).__init__(*args, **kwargs)
        self.datapaths = {}          # dpid -> datapath
        self.prev = {}               # (dpid, port) -> (time, rx_bytes, tx_bytes)

        # policy
        try:
            self.policy = load_policy(POLICY_PATH)
            self.logger.info("Policy loaded from %s", POLICY_PATH)
        except (OSError, ValueError) as e:
            self.logger.error("Cannot load policy at start-up (%s). "
                              "Using deny-all fallback.", e)
            self.policy = FALLBACK_POLICY
        self.policy_mtime = self._mtime()

        # bandwidth csv
        os.makedirs(os.path.dirname(BW_CSV_PATH), exist_ok=True)
        if not os.path.exists(BW_CSV_PATH) or os.path.getsize(BW_CSV_PATH) == 0:
            with open(BW_CSV_PATH, "w", newline="") as f:
                csv.writer(f).writerow(
                    ["time", "switch", "port", "host", "rx_mbps", "tx_mbps"])

        self.reload_thread = hub.spawn(self._policy_loop)
        self.monitor_thread = hub.spawn(self._monitor_loop)

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _mtime():
        try:
            return os.path.getmtime(POLICY_PATH)
        except OSError:
            return None

    # -- switch connection --------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        self.logger.info("Switch %s connected", dp.id)
        self.install(dp)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
        elif ev.state == DEAD_DISPATCHER:
            self.datapaths.pop(dp.id, None)
            self.logger.info("Switch %s disconnected", dp.id)

    # -- flow installation --------------------------------------------------
    def _add_flow(self, dp, priority, match_fields, allow):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        match = parser.OFPMatch(**match_fields)
        if allow:
            actions = [parser.OFPActionOutput(ofp.OFPP_NORMAL)]
            inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        else:
            inst = []          # no instructions = drop
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=priority,
                                      match=match, instructions=inst))

    def install(self, dp):
        """Delete all flows, then install baseline + policy flows."""
        ofp, parser = dp.ofproto, dp.ofproto_parser

        # 1. delete everything
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, command=ofp.OFPFC_DELETE, table_id=ofp.OFPTT_ALL,
            out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
            match=parser.OFPMatch()))

        # 2. baseline: match everything -> NORMAL (priority 1)
        self._add_flow(dp, BASELINE_PRIORITY, {}, True)

        # 3. policy flows
        for prio, match, act, rid in build_flows(self.policy):
            self._add_flow(dp, prio, match, act == "allow")
            self.logger.info("Rule %s %s prio=%d %s", rid, act.upper(), prio,
                             match.get("ipv4_src", "*") if "tcp_dst" in match
                             else "(reply) -> " + match.get("ipv4_dst", "*"))

    # -- live reload --------------------------------------------------------
    def _policy_loop(self):
        while True:
            hub.sleep(CHECK_INTERVAL)
            mtime = self._mtime()
            if mtime is None or mtime == self.policy_mtime:
                continue
            self.policy_mtime = mtime
            try:
                new_policy = load_policy(POLICY_PATH)
            except (OSError, ValueError) as e:
                self.logger.warning("Policy file changed but is invalid (%s). "
                                    "Keeping the old policy.", e)
                continue
            self.policy = new_policy          # one assignment
            self.logger.info("Policy reloaded at %s", time.strftime("%H:%M:%S"))
            for dp in list(self.datapaths.values()):
                self.install(dp)

    # -- bandwidth monitor --------------------------------------------------
    def _monitor_loop(self):
        while True:
            for dp in list(self.datapaths.values()):
                parser, ofp = dp.ofproto_parser, dp.ofproto
                dp.send_msg(parser.OFPPortStatsRequest(dp, 0, ofp.OFPP_ANY))
            hub.sleep(CHECK_INTERVAL)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        dp = ev.msg.datapath
        ofp = dp.ofproto
        now = time.time()
        rows = []

        for stat in ev.msg.body:
            port = stat.port_no
            if port > ofp.OFPP_MAX:            # skip LOCAL etc.
                continue
            key = (dp.id, port)
            old = self.prev.get(key)
            self.prev[key] = (now, stat.rx_bytes, stat.tx_bytes)
            if old is None:                    # first reading: nothing to compare
                continue
            dt = now - old[0]
            if dt <= 0:
                continue
            rx = (stat.rx_bytes - old[1]) * 8 / dt / 1e6
            tx = (stat.tx_bytes - old[2]) * 8 / dt / 1e6
            rows.append(["%.1f" % now, "s%d" % dp.id, port, "h%d" % port,
                         "%.2f" % rx, "%.2f" % tx])

        if not rows:
            return
        with open(BW_CSV_PATH, "a", newline="") as f:
            csv.writer(f).writerows(rows)
        for r in sorted(rows, key=lambda r: r[2]):
            if float(r[4]) > PRINT_THRESHOLD_MBPS or float(r[5]) > PRINT_THRESHOLD_MBPS:
                self.logger.info("%s port %s (%s): rx %6s Mbps  tx %6s Mbps",
                                 r[1], r[2], r[3], r[4], r[5])
