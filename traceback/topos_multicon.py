from mininet.net import Mininet
from mininet.topo import Topo
from mininet.topolib import TreeTopo
from mininet.node import OVSSwitch, RemoteController

c1 = RemoteController('c1', ip = '127.0.0.1', port = 6633)
c2 = RemoteController('c2', ip = '127.0.0.1', port = 6634)
cmap = {'s1': c1, 's2': c1, 's3': c2, 's4': c2}

class TwoNetworks(Topo):

  # TOPOLOGY:
  #
  #   h1---s1---g1---s3---h3
  #            /  \
  #   h2---s2_/    \_s4---h4
  #   (g1 is a host configured to act as a gateway)
  #   
  #   LEFT: 12.0.0.0 MASK 255.255.255.0
  #   
  #   RIGHT: 34.0.0.0 MASK 255.255.255.0
  #
  # 

  def __init__(self):
    Topo.__init__(self)
    num_switches = 4
    s = [None] * (num_switches + 1)
    
    # Create switches
    for i in range(1, num_switches + 1):
      s[i] = self.addSwitch('s{}'.format(i))

    # Create and hook up hosts.
    host = self.addHost('h1')
    self.addLink(host, s[1])
    host = self.addHost('h2')
    self.addLink(host, s[2])
    host = self.addHost('h3')
    self.addLink(host, s[3])
    host = self.addHost('h4')
    self.addLink(host, s[4])

    # Create and hook up gateway host.
    gateway = self.addHost('g1')
    for i in range(1, num_switches + 1):
      self.addLink(gateway, s[i])

class MultiSwitch(OVSSwitch):
  def start(self, controllers):
    return OVSSwitch.start(self, [cmap[self.name]])

# topo = TwoNetworks()
topo = TreeTopo(depth = 2, fanout = 2)
net = Mininet(topo = topo, switch = MultiSwitch, build = False)
for c in [c1, c2]:
    net.addController(c)
net.build()
net.start()
# # Assign IPs to the hosts
# net['h1'].setIP('12.0.0.1')
# net['h2'].setIP('12.0.0.2')
CLI(net)
net.stop()
