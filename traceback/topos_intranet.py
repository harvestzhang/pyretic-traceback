from mininet.topo import Topo

class Two_Ingress(Topo):

  # TOPOLOGY:
  #
  #    s4----h4
  #     |
  #    s3----h3
  #   /  \
  #  s1   s2 (gateways)
  #  |     |
  #  ex1   ex2 (external hosts)

  def __init__(self):
    Topo.__init__(self)
    num_switches = 4
    s = [None] * (num_switches + 1)
    
    # Create switches
    for i in range(1, num_switches + 1):
      s[i] = self.addSwitch('s{}'.format(i))

    # Link up the switches.
    self.addLink(s[1], s[3])
    self.addLink(s[2], s[3])
    self.addLink(s[3], s[4])

    # Create and hook up hosts.
    host = self.addHost('h3')
    self.addLink(host, s[3])
    host = self.addHost('h4')
    self.addLink(host, s[4])
    
    # Create and hook up external hosts.
    exthost = self.addHost('ex1')
    self.addLink(exthost, s[1])
    exthost = self.addHost('ex2')
    self.addLink(exthost, s[2])

class Four_Ingress(Topo):

  # TOPOLOGY:
  #
  #   h7      h8         h9         h10
  #   |        |         |           |
  #  s5 ----- s6 ------ s7 --------- s8
  #   |        |         |            
  #  s1 ----- s2        s3 --------- s4
  #   |       |       /    \       /   \
  # ex1     ex2     ex3    ex4   ex5   ex6
  #

  def __init__(self):
    Topo.__init__(self)
    num_switches = 8
    s = [None] * (num_switches + 1)

    # Create switches
    for i in range(1, num_switches + 1):
      s[i] = self.addSwitch('s{}'.format(i))

    # Link up the switches
    self.addLink(s[1], s[2])
    self.addLink(s[1], s[5])
    self.addLink(s[2], s[6])
    self.addLink(s[3], s[4])
    self.addLink(s[3], s[7])
    self.addLink(s[5], s[6])
    self.addLink(s[6], s[7])
    self.addLink(s[7], s[8])

    # Create and hook up hosts.
    for i in range(7, 11):
      host = self.addHost('h{}'.format(i))
      self.addLink(host, s[i - 2])

    # Create and hook up external hosts.
    host = self.addHost('ex1')
    self.addLink(host, s[1])
    host = self.addHost('ex2')
    self.addLink(host, s[2])
    host = self.addHost('ex3')
    self.addLink(host, s[3])
    host = self.addHost('ex4')
    self.addLink(host, s[3])
    host = self.addHost('ex5')
    self.addLink(host, s[4])
    host = self.addHost('ex6')
    self.addLink(host, s[4])

class Three_Switch(Topo):

  # TOPOLOGY:
  #
  #    s1----s2----s3
  #     |     |     |
  #    h1    h2    h3
  #

  def __init__(self):
    Topo.__init__(self)
    num_switches = 3
    s = [None] * (num_switches + 1)
    
    # Create switches
    for i in range(1, num_switches + 1):
      s[i] = self.addSwitch('s{}'.format(i))

    # Link up the switches.
    self.addLink(s[1], s[2])
    self.addLink(s[2], s[3])

    # Create and hook up hosts.
    host = self.addHost('h1')
    self.addLink(host, s[1])
    host = self.addHost('h2')
    self.addLink(host, s[2])
    host = self.addHost('h3')
    self.addLink(host, s[3])

topos = {
  'two_ingress': Two_Ingress,
  'four_ingress': Four_Ingress,
  'three_switch': Three_Switch,
}
