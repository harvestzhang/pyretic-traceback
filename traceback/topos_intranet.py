from mininet.topo import Topo

class Two_Ingress(Topo):

  # TOPOLOGY:
  #
  #    s4[2]---h4
  #    [1]
  #     |
  #    [3]
  #    s3[4]---h3
  #   [1] [2]
  #   /     \
  # [1]     [1]
  #  s1     s2 (gateways)
  # [2]     [2]
  #  |       |
  # h1       h2 (external hosts)

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
    host = self.addHost('h1')
    self.addLink(host, s[1])
    host = self.addHost('h2')
    self.addLink(host, s[2])
    host = self.addHost('h3')
    self.addLink(host, s[3])
    host = self.addHost('h4')
    self.addLink(host, s[4])

class Four_Ingress(Topo):

  # TOPOLOGY:
  #
  #   h7      h8         h9         h10
  #   |        |         |           |
  #  s5 ----- s6 ------ s7 --------- s8
  #   |        |         |            
  #  s1 ----- s2        s3 --------- s4
  #   |        |      /    \       /   \
  #  h1       h2     h3    h4     h5   h6
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

    # Create and hook up the other hosts.
    host = self.addHost('h1')
    self.addLink(host, s[1])
    host = self.addHost('h2')
    self.addLink(host, s[2])
    host = self.addHost('h3')
    self.addLink(host, s[3])
    host = self.addHost('h4')
    self.addLink(host, s[3])
    host = self.addHost('h5')
    self.addLink(host, s[4])
    host = self.addHost('h6')
    self.addLink(host, s[4])

class Two_Switch(Topo):

  # TOPOLOGY:
  #
  #    s1----s2
  #     |     |
  #    h1    h2
  #

  def __init__(self):
    Topo.__init__(self)
    
    # Create switches
    s1 = self.addSwitch('s1')
    s2 = self.addSwitch('s2')

    # Link up the switches.
    self.addLink(s1, s2)

    # Create and hook up hosts.
    host = self.addHost('h1')
    self.addLink(host, s1)
    host = self.addHost('h2')
    self.addLink(host, s2)

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
  'two_switch': Two_Switch,
  'two_ingress': Two_Ingress,
  'four_ingress': Four_Ingress,
  'three_switch': Three_Switch,
}
