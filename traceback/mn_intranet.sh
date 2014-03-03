#!/bin/bash

sudo ~/pyretic/mininet/mn -c
sudo ~/pyretic/mininet/mn --custom topos_intranet.py --controller remote --mac --topo $@
