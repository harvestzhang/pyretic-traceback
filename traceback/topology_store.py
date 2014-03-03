from pyretic.lib.corelib import *
from pyretic.lib.std import *

# -------------------------------------------------------------
# A policy that does nothing but store the network topology.
# -------------------------------------------------------------
class Topology_store(DynamicPolicy):
  def __init__(self):
    self.network = None
    super(topology_store, self).__init__()

  def set_network(self, network):
    self.network = network

  def get_topology(self):
    return self.network.topology