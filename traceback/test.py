# TESTS VIRTUAL HEADERS AND INSTALLED RULES

from pyretic.lib.corelib import *
from pyretic.lib.std import *
from pyretic.lib.query import *
from pyretic.modules.mac_learner import mac_learner

policy = None

def look_at_packet(packet):
  print
  print '**************** look_at_packet() called ****************'
  print packet
  print '*********************************************************'
  print

  rules = policy.compile().rules
  for rule in rules:
    print rule

def tag():
    return if_(match(switch = 1), modify(v_header = 7))

def flag():
  m_flag = match(switch = 3)
  q_flag = packets(limit = 1, group_by = ['srcip'])
  q_flag.register_callback(look_at_packet)
  return m_flag >> q_flag

def untag():
  m_untag = ~match(v_header = None) & egress_network()
  return if_(m_untag, modify(v_header = None))

def main():
  global policy
  policy = tag() >> mac_learner() >> (flag() + untag())
  print policy
  return policy