from pyretic.lib.corelib import *
from pyretic.lib.std import *

from policy_traceback import *

from collections import deque
import ipdb

# Link color constants
BLACK = 0
RED = 1
GREEN = 2

# ------------------------------------------------------------------------------
# Takes a tagged ingress switch and plays it forward to figure out its path
# through the network.
# 
# > Uses virtual header space to store an ingress tag.
# > Not robust to packet modification.
# ------------------------------------------------------------------------------
def ingress_tagging(policy, topo, packet):
  in_switch = packet['in_switch']
  in_port = packet['in_port']
  flag_switch = packet['switch']

  # Start at ingress
  print 'Ingress: switch s{} at port {}'.format(in_switch, in_port)
  pkt = packet.modify(switch = in_switch, port = in_port)

  # Trace packet
  cur_switch = in_switch
  while (True):
    pkt = policy.dry_eval(pkt).pop()
    port = pkt['outport']
    
    # Print traceback output; stop if at end
    print '--> switch s{} forwards out port {}'.format(cur_switch, port)
    if cur_switch == flag_switch:
      print 'to host.'
      break
    
    # Hop the packet to the next switch
    next_switch = topo.dst_switch(cur_switch, port)
    if not next_switch:
      print 'Switch at port not found. Stopping traceback, starting debugger.'
      ipdb.set_trace()
      return
    pkt = pkt.modify(switch = next_switch)
    cur_switch = next_switch

# ------------------------------------------------------------------------------
# 
# ------------------------------------------------------------------------------
def backstep(policy, topo, packet):
  rules = policy.compile().rules
  start_switch = PathSwitch(packet['switch'])
  path_switches = [start_switch]
  explore_switches = deque()
  explore_switches.append(start_switch)

  while len(explore_switches) > 0:

    pathswitch = explore_switches.popleft()
    neighbors = topo.edge[pathswitch.switch]

    for neighbor in neighbors:
      port = neighbors[neighbor][neighbor] # port from neighbor to us
      
      for abs_pkt in pathswitch.abs_pkts:

        for rule in rules:
          if type(rule.match) == type(identity):
           continue
          match = rule.match.map # dict
          actions = rule.actions # list

          # We only care if the rule is about the neighbor switch, and if it has
          # a rule installed for the given packet flow
          if ('switch' in match and match['switch'] == neighbor and
              'srcmac' in match and match['srcmac'] == pkt['srcmac'] and
              'dstmac' in match and match['dstmac'] == pkt['dstmac']
             ):
            for action in actions:
              if type(action) == modify:
                mods = action.map
                # If the rule forwards to the right switch, examine further!
                if 'outport' in mods and mods['outport'] == port:
                  explore_switches.append(SwitchPacket(neighbor, pkt))

class PathSwitch:

  def __init__(self, switch):
    self.switch = switch
    abs_pkts = {}

  def pkt_explored(self, abs_pkt):
    return abs_pkt in self.abs_pkts

  def add_abs_pkt(self, abs_pkt, dst_switch):
    abs_pkts[abs_pkt] = dst_switch

class AbstractPacket:
  
  def __init__(self, packet):
    self.packet = packet

# ------------------------------------------------------------------------------
#
#
#
# ------------------------------------------------------------------------------
def policy_inversion(policy, topo, packet):

  tb_switch = packet.header['switch']
  tb_policy = traceback_policy(policy, topo)
  ingresses = {1:MAC('00:00:00:00:00:01'), 2:MAC('00:00:00:00:00:02')}
  #ingresses = [(loc.switch, loc.port_no) for loc in list(topo.egress_locations())]

  fwd_pkts = []
  pkts = [packet]
  print 'Starting at switch', tb_switch, 'at port', packet.header['inport']
  
  while len(pkts) > 0:
    print '< < < < < < < <'
    
    back_pkts = []
    for pkt in pkts:
      back_pkts += (list(tb_policy.dry_eval(pkt)))
    
    pkts = []
    for pkt in back_pkts:
      
      # Update packet list for next round
      if 'inport' in pkt.header:
        print 'Switch', pkt.header['switch'], 'with in port', pkt.header['inport']
      else:
        print 'Switch', pkt.header['switch'], 'at beginning.'
      pkts.append(pkt)

      # See if any hosts at this switch could've sent the packet
      switch = pkt.header['switch']
      if switch in ingresses and pkt.header['srcmac'] == ingresses[switch]:
        fwd_pkts.append(pkt)

  fwd_policy = policy >> topo_policy(topo)
  for fwd_pkt in fwd_pkts:
    print
    print '*** Possible path: ***'
    while pkt.header['switch'] is not tb_switch:
      print
      print '>>>'
      print
      print fwd_pkt
      out_pkts = fwd_policy.dry_eval(fwd_pkt)
      if len(out_pkts) == 1:
        fwd_pkt = out_pkts.pop()
      else:
        break
    print '**********************'
    print

  
