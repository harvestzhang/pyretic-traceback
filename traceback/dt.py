from pyretic.lib.corelib import *
from pyretic.lib.std import *
from pyretic.lib.query import *
from pyretic.modules.mac_learner import mac_learner

import intradomain_traceback

import threading, os, signal # For CLI

policy = None
flag = None

# ------------------------------------------------------------------------------
# Print out the intradomain packet trace.
# ------------------------------------------------------------------------------
def trace_packet(packet):
  global policy
  global flag

  # Refresh topology
  topo = flag.get_topology()

  # Print the packet for debugging purposes
  print
  print '**************** NEW FLOW TRACEBACK ****************'
  print packet
  print '****************************************************'

  # # Print ingress tagging traceback
  # print
  # print '**************** INGRESS TAGGING: ******************'
  # intradomain_traceback.ingress_tagging(policy, topo, packet)
  # print '****************************************************'

  # # Print backstep traceback
  # print
  # print '**************** BACKSTEP: *****************'
  # intradomain_traceback.backstep(policy, topo, packet)
  # print '****************************************************'  

  # Print policy inversion traceback
  print
  print '**************** POLICY INVERSION: *****************'
  intradomain_traceback.policy_inversion(policy, topo, packet)
  print '****************************************************'  

# ------------------------------------------------------------------------------
# UI loop that lets the user dynamically choose the switch/host at which to
# perform tracebacks.
# 
# Currently available commands are:
# 
# >> clear :  Removes any existing switch/host for tracebacks
# >> info  :  Prints out current traceback switch/host status
# >> exit  :  Exits.
# >> X Y   :  Sets traceback up at switch X's host Y
# ------------------------------------------------------------------------------
class flag(DynamicPolicy):

  def __init__(self):
    super(flag, self).__init__()
    self.network = None
    self.switch = None
    self.hostmac = None
    
    # Dummy for testing
    # m_flagged_switch = match(switch = 4, dstmac = MAC('00:00:00:00:00:04'))
    # q_flagged_packets = packets(limit = 1, group_by = ['srcip'])
    # q_flagged_packets.register_callback(trace_packet)
    # self.policy = m_flagged_switch >> q_flagged_packets

    self.policy = drop
    self.cli = threading.Thread(target = self.cli_loop)
    self.cli.daemon = True
    self.cli.start()

  def set_network(self, network):
    self.network = network

  def get_topology(self):
    return self.network.topology

  def cli_loop(self):
    while(True):
      user_cmd = raw_input()
      
      if user_cmd == 'clear':
        self.policy = drop
        self.switch = None
        self.hostmac = None
      
      elif user_cmd == 'info':
        pass
      
      elif user_cmd == 'exit':
        print '---------------------'
        print 'EXITING.'
        print '---------------------'
        os.kill(os.getpid(), signal.SIGINT)
        return
      
      else:
        cmd_params = user_cmd.split()
        if len(cmd_params) != 2:
          print '---------------------'
          print 'Oops, that didn\'t work. Give me a switch number followed by host number (ex. \'2 5\' for host 5 attached to switch 2)'
          print '---------------------'
          continue
        self.switch = int(cmd_params[0])
        self.hostmac = MAC('00:00:00:00:00:{:02x}'.format(int(cmd_params[1]))) # TODO FIX MAC ID
        m_flagged_switch = match(switch = self.switch, dstmac = self.hostmac) # use & ~match(in_switch = None) to force tagging only
        q_flagged_packets = packets(limit = 1, group_by = ['srcip'])
        q_flagged_packets.register_callback(trace_packet)
        self.policy = m_flagged_switch >> q_flagged_packets
      
      self.print_flag_status()

  def print_flag_status(self):
    if not self.switch or not self.hostmac:
      print '---------------------'
      print 'NO CURRENT TRACEBACK.'
      print '---------------------'
    else:
      print '---------------------'
      print 'TRACING PACKETS TO HOST MAC {} AT SWITCH s{}.'.format(self.hostmac, self.switch)
      print '---------------------'    

# ------------------------------------------------------------------------------
# Tag all packets that haven't already been tagged with ingress
# switch number
# ------------------------------------------------------------------------------
def tag():
  tag_policy = if_(match(in_switch = None, in_port = None), modify(in_switch = 'switch', in_port = 'inport'))
  return tag_policy

# ------------------------------------------------------------------------------
# Untag any egress packet if it has an ingress tag.
# ------------------------------------------------------------------------------
def untag():
  m_untag = ~match(in_switch = None, in_port = None) & egress_network()
  return if_(m_untag, modify(in_switch = None, in_port = None))

# ------------------------------------------------------------------------------
# Tags at each switch, then does mac learning. At host, packets
# are untagged and some are flagged for traceback.
# ------------------------------------------------------------------------------
def main():
  global policy
  global flag

  flag = flag()
  # policy = tag() >> mac_learner() >> (flag + untag()) Don't need tagging
  policy = mac_learner() + flag
  print policy
  return policy
