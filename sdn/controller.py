import json
import os
import time
import ipaddress

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub

class PolicyController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(PolicyController, self).__init__(*args, **kwargs)
        self.datapaths = {}
        self.policy_file = 'sdn/policy.json'
        self.last_mtime = 0
        self.current_policy = None
        self.monitor_thread = hub.spawn(self._monitor_policy)

    def load_policy(self, path):
        with open(path, 'r') as f:
            policy = json.load(f)
        
        # Validation checks
        if policy['default_action'] not in ['allow', 'deny']:
            raise ValueError("default_action must be 'allow' or 'deny'")
        if not isinstance(policy['server_port'], int):
            raise ValueError("server_port must be an integer")
        ipaddress.IPv4Address(policy['server_ip'])
        
        for rule in policy.get('rules', []):
            if rule['action'] not in ['allow', 'deny']:
                raise ValueError("Rule action must be 'allow' or 'deny'")
            if rule['src_ip'] != "*":
                ipaddress.IPv4Address(rule['src_ip'])
                
        return policy

    def build_flows(self, policy):
        flows = []
        server_ip = policy['server_ip']
        server_port = policy['server_port']
        
        # Baseline NORMAL flow
        flows.append({'priority': 1, 'match': {}, 'action': 'allow', 'desc': 'baseline'})

        # Default action flows (Priority 10)
        if policy['default_action'] == 'deny':
            flows.append({
                'priority': 10, 
                'match': {'eth_type': 0x0800, 'ip_proto': 6, 'ipv4_dst': server_ip, 'tcp_dst': server_port}, 
                'action': 'deny', 'desc': 'default_deny_c2s'
            })
            flows.append({
                'priority': 10, 
                'match': {'eth_type': 0x0800, 'ip_proto': 6, 'ipv4_src': server_ip, 'tcp_src': server_port}, 
                'action': 'deny', 'desc': 'default_deny_s2c'
            })

        # Policy Rules (Priority 1000 - k)
        for k, rule in enumerate(policy.get('rules', [])):
            prio = 1000 - k
            client_ip = rule['src_ip']
            action = rule['action']
            rule_id = rule.get('id', 'N/A')

            # Client to Server
            match_c2s = {'eth_type': 0x0800, 'ip_proto': 6, 'ipv4_dst': server_ip, 'tcp_dst': server_port}
            if client_ip != "*":
                match_c2s['ipv4_src'] = client_ip
            flows.append({'priority': prio, 'match': match_c2s, 'action': action, 'id': rule_id, 'src_ip': client_ip})

            # Server to Client
            match_s2c = {'eth_type': 0x0800, 'ip_proto': 6, 'ipv4_src': server_ip, 'tcp_src': server_port}
            if client_ip != "*":
                match_s2c['ipv4_dst'] = client_ip
            flows.append({'priority': prio, 'match': match_s2c, 'action': action})

        return flows

    def install(self, datapath, flows):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # 1. Delete all existing flows
        empty_match = parser.OFPMatch()
        delete_mod = parser.OFPFlowMod(
            datapath=datapath, command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
            match=empty_match, table_id=ofproto.OFPTT_ALL
        )
        datapath.send_msg(delete_mod)

        # 2. Install new flows
        for f in flows:
            match = parser.OFPMatch(**f['match'])
            actions = []
            
            if f['action'] == 'allow':
                actions = [parser.OFPActionOutput(ofproto.OFPP_NORMAL)]
            # If 'deny', actions remains empty which drops the packet
            
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            flow_mod = parser.OFPFlowMod(
                datapath=datapath, priority=f['priority'], 
                match=match, instructions=inst
            )
            datapath.send_msg(flow_mod)

            # Log rule installation
            if 'id' in f:
                self.logger.info("[POLICY] Installed - Rule ID: %s, Action: %s, Source: %s", f['id'], f['action'].upper(), f['src_ip'])

    def _monitor_policy(self):
        while True:
            try:
                if os.path.exists(self.policy_file):
                    mtime = os.path.getmtime(self.policy_file)
                    if mtime != self.last_mtime:
                        try:
                            new_policy = self.load_policy(self.policy_file)
                            self.current_policy = new_policy
                            self.last_mtime = mtime
                            self.logger.info("[RELOAD] Successfully loaded new policy from %s", self.policy_file)
                            
                            flows = self.build_flows(self.current_policy)
                            for datapath in self.datapaths.values():
                                self.install(datapath, flows)
                        except Exception as e:
                            self.logger.warning("[ERROR] Broken policy file detected: %s. Keeping old policy.", e)
            except Exception as e:
                self.logger.error("Error checking policy file: %s", e)
                
            hub.sleep(2)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        self.datapaths[datapath.id] = datapath
        if self.current_policy:
            flows = self.build_flows(self.current_policy)
            self.install(datapath, flows) 
