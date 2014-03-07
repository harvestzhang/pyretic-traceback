# Implements back policies for given policies, as well as test code.

from pyretic.lib.corelib import *
from pyretic.lib.std import *
from pyretic.lib.query import *
import ipdb
import sys

def back_policy(policy):

  # identity and match map onto themselves.
  # drop has an undefined back policy "ndef", but we'll never need to deal with it
  if policy is identity or policy is drop or isinstance(policy, match):
    return policy
  
  # back(modify(f=v)) = match(f=v) >> {modify(f=v') for all v'}
  elif isinstance(policy, modify):
    backpol = match(policy.map) >> sum_modify([f for f in policy.map])
    return backpol

  # back(p1 >> p2) = back(p2) >> back(p1)
  elif isinstance(policy, sequential):
    
    # If there was a drop/Query/Controller in there, that's an implicit drop backwards.
    if drop in policy.policies or any(p is Controller or isinstance(p, Query) for p in policy.policies):
      return drop
    
    # Simplify the policy by getting rid of any identities in sequential
    simp_policies = [p for p in policy.policies if p is not identity]

    # Reverse the policy
    backpol_list = [back_policy(p) for p in simp_policies[::-1]]
    if isinstance(policy, intersection):
      backpol = intersection(backpol_list)
    else:
      backpol = sequential(backpol_list)
    return backpol

  # back(p1 + p2) = back(p1) + back(p2)
  elif isinstance(policy, parallel):
    backpol_list = [back_policy(p) for p in policy.policies]
    if isinstance(policy, union):
      backpol = union(backpol_list)
    else:
      backpol = parallel(backpol_list)
    return backpol

  # back(~p) = ~back(p)
  elif isinstance(policy, negate):
    return negate([back_policy(policy.policies[0])])
  
  # Packet isn't forwarded out a port, so just drop backwards
  elif policy is Controller or isinstance(policy, Query):
    return drop

  # Back of a link in a topology is just the opposite direction
  elif isinstance(policy, link):
    backpol = link(policy.inswitch, policy.inport, policy.outswitch, policy.outport)
    return backpol

  # Apply back policy algorithm to the underlying policy of Derived policies
  elif isinstance(policy, DerivedPolicy):
    return back_policy(policy.policy)

  # Something went horribly wrong. Stop - Debug time!
  else:
    ipdb.set_trace()

def topo_policy(topo):
  edges = topo.edge
  all_links = []
  for s1 in edges:
    adj = edges[s1]
    for s2 in adj:
      all_links.append(link(s1, adj[s2][s1], s2, adj[s2][s2]))
  return parallel(all_links)

class topo_store(DynamicPolicy):
  
  def __init__(self):
      self.network = None
      super(topo_store,self).__init__()
      self.policy = packets(limit = 1, group_by = ['srcip'])
      self.policy.register_callback(self.check_topo)
  
  def set_network(self, network):
      self.network = network
  
  def get_topo(self):
      return self.network.topology
  
  def check_topo(self, packet):
      test_back_policy(topo_policy(self.get_topo()))

  def __repr__(self):
      return "topo_store"

def test_back_policy(policy):
  print
  print '----------------------------------------------------------------------'
  print
  print '******************* Policy *********************'
  print
  print policy
  print
  simplified = simplify_tb(policy)
  print '************** Simplified Policy ***************'
  print
  print simplified
  print
  back = back_policy(simplified)
  print '***************** Back Policy ******************'
  print
  print back
  print
  simplified_back = simplify_tb(back)
  print '*********** Simplified Back Policy *************'
  print
  print simplified_back
  print

def main():
  print
  print "############### Sequential policy simplification and traceback"
  policy = match(dstmac = 1) >> match(switch = 4) >> match(switch = 5)
  test_back_policy(policy)
  policy = match(switch = 3) >> modify(switch = 10)
  test_back_policy(policy)
  policy = if_(match(switch = 3), modify(switch = 10))
  test_back_policy(policy)
  sys.exit(0)

  # Below is for testing topology policies
  # policy = topo_store()
  # return policy
