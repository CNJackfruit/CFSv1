from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3

class BaselineController(app_manager.RyuApp):
    # Use the OpenFlow 1.3 parser as requested[cite: 14]
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(BaselineController, self).__init__(*args, **kwargs)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # 1. Delete all old flows when the switch connects
        empty_match = parser.OFPMatch()
        delete_mod = parser.OFPFlowMod(
            datapath=datapath, 
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY, 
            out_group=ofproto.OFPG_ANY,
            match=empty_match,
            table_id=ofproto.OFPTT_ALL
        )
        datapath.send_msg(delete_mod)

        # 2. Install the baseline flow: match everything, priority 1, action NORMAL[cite: 14, 15]
        actions = [parser.OFPActionOutput(ofproto.OFPP_NORMAL)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        
        normal_mod = parser.OFPFlowMod(
            datapath=datapath, 
            priority=1, 
            match=empty_match, 
            instructions=inst
        )
        datapath.send_msg(normal_mod)
        self.logger.info("Baseline NORMAL flow installed on switch.")
        
