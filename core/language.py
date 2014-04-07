
################################################################################
# The Pyretic Project                                                          #
# frenetic-lang.org/pyretic                                                    #
# author: Joshua Reich (jreich@cs.princeton.edu)                               #
# author: Christopher Monsanto (chris@monsan.to)                               #
# author: Cole Schlesinger (cschlesi@cs.princeton.edu)                         #
################################################################################
# Licensed to the Pyretic Project by one or more contributors. See the         #
# NOTICES file distributed with this work for additional information           #
# regarding copyright and ownership. The Pyretic Project licenses this         #
# file to you under the following license.                                     #
#                                                                              #
# Redistribution and use in source and binary forms, with or without           #
# modification, are permitted provided the following conditions are met:       #
# - Redistributions of source code must retain the above copyright             #
#   notice, this list of conditions and the following disclaimer.              #
# - Redistributions in binary form must reproduce the above copyright          #
#   notice, this list of conditions and the following disclaimer in            #
#   the documentation or other materials provided with the distribution.       #
# - The names of the copyright holds and contributors may not be used to       #
#   endorse or promote products derived from this work without specific        #
#   prior written permission.                                                  #
#                                                                              #
# Unless required by applicable law or agreed to in writing, software          #
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT    #
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the     #
# LICENSE file distributed with this work for specific language governing      #
# permissions and limitations under the License.                               #
################################################################################
import ipdb # TEMPORARY

# This module is designed for import *.
import functools
import itertools
import struct
import time
from ipaddr import IPv4Network
from bitarray import bitarray

from pyretic.core import util
from pyretic.core.network import *
from pyretic.core.util import frozendict, singleton

from multiprocessing import Condition

basic_headers = ["srcmac", "dstmac", "srcip", "dstip", "tos", "srcport", "dstport",
                 "ethtype", "protocol"]
tagging_headers = ["vlan_id", "vlan_pcp"]
native_headers = basic_headers + tagging_headers
location_headers = ["switch", "inport", "outport"]
compilable_headers = native_headers + location_headers
content_headers = [ "raw", "header_len", "payload_len"]

################################################################################
# Policy Language                                                              #
################################################################################

class Policy(object):
    """
    Top-level abstract class for policies.
    All Pyretic policies have methods for

    - evaluating on a single packet.
    - compilation to a switch Classifier
    """
    def eval(self, pkt):
        """
        evaluate this policy on a single packet

        :param pkt: the packet on which to be evaluated
        :type pkt: Packet
        :rtype: set Packet
        """
        raise NotImplementedError

    def dry_eval(self, pkt):
        return self.eval(pkt)


    def compile(self):
        """
        Produce a Classifier for this policy

        :rtype: Classifier
        """
        raise NotImplementedError

    def __add__(self, pol):
        """
        The parallel composition operator.

        :param pol: the Policy to the right of the operator
        :type pol: Policy
        :rtype: Parallel
        """
        if isinstance(pol,parallel):
            return parallel([self] + pol.policies)
        else:
            return parallel([self, pol])

    def __rshift__(self, other):
        """
        The sequential composition operator.

        :param pol: the Policy to the right of the operator
        :type pol: Policy
        :rtype: Sequential
        """
        if isinstance(other,sequential):
            return sequential([self] + other.policies)
        else:
            return sequential([self, other])

    def __eq__(self, other):
        """Syntactic equality."""
        raise NotImplementedError

    def __ne__(self,other):
        """Syntactic inequality."""
        return not (self == other)

    def name(self):
        return self.__class__.__name__

    def __repr__(self):
        return "%s : %d" % (self.name(),id(self))


class Filter(Policy):
    """
    Abstact class for filter policies.
    A filter Policy will always either 

    - pass packets through unchanged
    - drop them

    No packets will ever be modified by a Filter.
    """
    def eval(self, pkt):
        """
        evaluate this policy on a single packet

        :param pkt: the packet on which to be evaluated
        :type pkt: Packet
        :rtype: set Packet
        """
        raise NotImplementedError

    def __or__(self, pol):
        """
        The Boolean OR operator.

        :param pol: the filter Policy to the right of the operator
        :type pol: Filter
        :rtype: Union
        """
        if isinstance(pol,Filter):
            return union([self, pol])
        else:
            raise TypeError

    def __and__(self, pol):
        """
        The Boolean AND operator.

        :param pol: the filter Policy to the right of the operator
        :type pol: Filter
        :rtype: Intersection
        """
        if isinstance(pol,Filter):
            return intersection([self, pol])
        else:
            raise TypeError

    def __sub__(self, pol):
        """
        The Boolean subtraction operator.

        :param pol: the filter Policy to the right of the operator
        :type pol: Filter
        :rtype: Difference
        """
        if isinstance(pol,Filter):
            return difference([self, pol])
        else:
            raise TypeError

    def __invert__(self):
        """
        The Boolean negation operator.

        :param pol: the filter Policy to the right of the operator
        :type pol: Filter
        :rtype: negate
        """
        return negate([self])


def _intersect_ip(ipfx, opfx):
    most_specific = None
    if (IPv4Network(ipfx) in IPv4Network(opfx)):
        most_specific = ipfx
    elif (IPv4Network(opfx) in IPv4Network(ipfx)): 
        most_specific = opfx
    return most_specific


class match(Filter):
    """
    Match on all specified fields.
    Matched packets are kept, non-matched packets are dropped.

    :param *args: field matches in argument format
    :param **kwargs: field matches in keyword-argument format
    """
    def __init__(self, *args, **kwargs):
        if len(args) == 0 and len(kwargs) == 0:
            raise TypeError
        self.map = util.frozendict(dict(*args, **kwargs))
        super(match,self).__init__()

    def eval(self, pkt):
        """
        evaluate this policy on a single packet

        :param pkt: the packet on which to be evaluated
        :type pkt: Packet
        :rtype: set Packet
        """

        for field, pattern in self.map.iteritems():
            try:
                v = pkt[field]
                if pattern is None or pattern != v:
                    return set()
            except:
                if pattern is not None:
                    return set()
        return {pkt}

    def compile(self):
        """
        Produce a Classifier for this policy

        :rtype: Classifier
        """
        r1 = Rule(self,[identity])
        r2 = Rule(identity,[drop])
        return Classifier([r1, r2])

    def __eq__(self, other):
        return ( (isinstance(other, match) and self.map == other.map)
            or (other == identity and len(self.map) == 0) )

    def intersect(self, pol):
        if pol == identity:
            return self
        elif pol == drop:
            return drop
        elif not isinstance(pol,match):
            raise TypeError
        fs1 = set(self.map.keys())
        fs2 = set(pol.map.keys())
        shared = fs1 & fs2
        most_specific_src = None
        most_specific_dst = None

        for f in shared:
            if (f=='srcip'):
                most_specific_src = _intersect_ip(self.map[f], pol.map[f])
                if most_specific_src is None:
                    return drop
            elif (f=='dstip'):
                most_specific_dst = _intersect_ip(self.map[f], pol.map[f])
                if most_specific_dst is None:
                    return drop
            elif (self.map[f] != pol.map[f]):
                return drop

        d = self.map.update(pol.map)

        if most_specific_src is not None:
            d = d.update({'srcip' : most_specific_src})
        if most_specific_dst is not None:
            d = d.update({'dstip' : most_specific_dst})

        return match(**d)

    def __and__(self,pol):
        if isinstance(pol,match):
            return self.intersect(pol)
        else:
            return super(match,self).__and__(pol)

    ### hash : unit -> int
    def __hash__(self):
        return hash(self.map)

    def covers(self,other):
        # Return identity if self matches every packet that other matches (and maybe more).
        # eg. if other is specific on any field that self lacks.
        if other == identity and len(self.map.keys()) > 0:
            return False
        elif other == identity:
            return True
        elif other == drop:
            return True
        if set(self.map.keys()) - set(other.map.keys()):
            return False
        for (f,v) in self.map.items():
            if (f=='srcip' or f=='dstip'):
                if(IPv4Network(v) != IPv4Network(other.map[f])):
                    if(not IPv4Network(other.map[f]) in IPv4Network(v)):
                        return False
            elif v != other.map[f]:
                return False
        return True

    def __repr__(self):
        return "match: %s" % ' '.join(map(str,self.map.items()))

@singleton
class identity(Filter):
    """The identity policy, leaves all packets unchanged."""
    def eval(self, pkt):
        """
        evaluate this policy on a single packet

        :param pkt: the packet on which to be evaluated
        :type pkt: Packet
        :rtype: set Packet
        """
        return {pkt}

    def compile(self):
        """
        Produce a Classifier for this policy

        :rtype: Classifier
        """
        return Classifier([Rule(identity, [identity])])

    def intersect(self, other):
        return other

    def covers(self, other):
        return True

    def __eq__(self, other):
        return ( id(self) == id(other)
            or ( isinstance(other, match) and len(other.map) == 0) )

    def __repr__(self):
        return "identity"

passthrough = identity   # Imperative alias
true = identity          # Logic alias
all_packets = identity   # Matching alias


@singleton
class drop(Filter):
    """The drop policy, produces the empty set of packets."""
    def eval(self, pkt):
        """
        evaluate this policy on a single packet

        :param pkt: the packet on which to be evaluated
        :type pkt: Packet
        :rtype: set Packet
        """
        return set()

    def compile(self):
        """
        Produce a Classifier for this policy

        :rtype: Classifier
        """
        return Classifier([Rule(identity, [drop])])

    def intersect(self, other):
        return self

    def covers(self, other):
        return False

    def __eq__(self, other):
        return id(self) == id(other)

    def __repr__(self):
        return "drop"

none = drop
false = drop             # Logic alias
no_packets = drop        # Matching alias


class modify(Policy):
    """
    Modify on all specified fields to specified values.

    :param *args: field assignments in argument format
    :param **kwargs: field assignments in keyword-argument format
    """
    ### init : List (String * FieldVal) -> List KeywordArg -> unit
    def __init__(self, *args, **kwargs):
        if len(args) == 0 and len(kwargs) == 0:
            raise TypeError
        self.map = dict(*args, **kwargs)
        self.has_virtual_headers = not \
            reduce(lambda acc, f:
                   acc and (f in compilable_headers),
                   self.map.keys(),
                   True)
        super(modify,self).__init__()

    def eval(self, pkt):
        """
        evaluate this policy on a single packet

        :param pkt: the packet on which to be evaluated
        :type pkt: Packet
        :rtype: set Packet
        """
        return {pkt.modifymany(self.map)}

    def compile(self):
        """
        Produce a Classifier for this policy

        :rtype: Classifier
        """
        if self.has_virtual_headers:
            r = Rule(identity,[Controller])
        else:
            r = Rule(identity,[self])
        return Classifier([r])

    def __repr__(self):
        return "modify: %s" % ' '.join(map(str,self.map.items()))

    def __eq__(self, other):
        return ( isinstance(other, modify)
           and (self.map == other.map) )

class sum_modify(Policy):
    """
    Abstract modify on all specified fields to a summation of values, represented
    as a match policy.

    :param *args: fields to sum over.
    """
    def __init__(self, *args):
        if len(args) != 1:
            raise TypeError
        self.fields = {}
        for field in args[0]:
            self.fields[field] = identity
        super(sum_modify, self).__init__()

    def eval(self, pkt):
        """
        Throws an error; no sum_modifies should be eval'd. All evalable modifies
        should already have been simplified to simple match-modifies.
        """
        raise RuntimeError("Can't eval a sum_modify.")

    def compile(self):
        """
        Throws an error; no sum_modifies should be eval'd. All evalable modifies
        should already have been simplified to simple match-modifies.
        """
        raise RuntimeError("Can't compile a sum_modify.")

    def restrict(self, field, policy): 
        self.fields[field] = simplify_tb(self.fields[field] >> policy)

    def __repr__(self):
        strform = "sum_modify:"
        for field in self.fields:
            strform += "\n    {}: {}".format(field, self.fields[field])
        return strform

    def __eq__(self, other):
        if not isinstance(other, sum_modify):
            return false
        if set(self.fields.keys()) != set(other.fields.keys()):
            return false
        for field in self.fields:
            if self.fields[field] != other.fields[field]:
                return false
        return true

@singleton
class Controller(Policy):
    def eval(self, pkt):
        return set()
    
    def compile(self):
        r = Rule(identity, [Controller])
        self._classifier = Classifier([r])
        return self._classifier

    def __eq__(self, other):
        return id(self) == id(other)

    def __repr__(self):
        return "Controller"
    

# FIXME: Srinivas =).
class Query(Filter):
    """
    Abstract class representing a data structure
    into which packets (conceptually) go and with which callbacks can register.
    """
    ### init : unit -> unit
    def __init__(self):
        from multiprocessing import Lock
        self.callbacks = []
        self.bucket = set()
        self.bucket_lock = Lock()
        super(Query,self).__init__()

    def eval(self, pkt):
        """
        evaluate this policy on a single packet

        :param pkt: the packet on which to be evaluated
        :type pkt: Packet
        :rtype: set Packet
        """
        with self.bucket_lock:
            self.bucket.add(pkt)
        return set()

    def dry_eval(self, pkt):
        return set()
        
    ### register_callback : (Packet -> X) -> unit
    def register_callback(self, fn):
        self.callbacks.append(fn)

    def __repr__(self):
        return "Query"


class FwdBucket(Query):
    """
    Class for registering callbacks on individual packets sent to
    the controller.
    """
    def compile(self):
        """Produce a Classifier for this policy

        :rtype: Classifier
        """
        r = Rule(identity,[Controller])
        return Classifier([r])

    def apply(self):
        with self.bucket_lock:
            for pkt in self.bucket:
                for callback in self.callbacks:
                    callback(pkt)
            self.bucket.clear()
    
    def __repr__(self):
        return "FwdBucket"

    def __eq__(self, other):
        # TODO: if buckets eventually have names, equality should
        # be on names.
        return isinstance(other, FwdBucket)


class CountBucket(Query):
    """
    Class for registering callbacks on counts of packets sent to
    the controller.
    """
    def __init__(self):
        super(CountBucket, self).__init__()
        self.matches = set([])
        self.runtime_stats_query_fun = None
        self.outstanding_switches = []
        self.packet_count = 0
        self.byte_count = 0
        self.packet_count_persistent = 0
        self.byte_count_persistent = 0
        self.in_update_cv = Condition()
        self.in_update = False
        
    def __repr__(self):
        return "CountBucket"

    def eval(self, pkt):
        """
        evaluate this policy on a single packet

        :param pkt: the packet on which to be evaluated
        :type pkt: Packet
        :rtype: set Packet
        """
        return set()

    def compile(self):
        """
        Produce a Classifier for this policy

        :rtype: Classifier
        """
        r = Rule(identity,[self])
        return Classifier([r])

    def apply(self):
        with self.bucket_lock:
            for pkt in self.bucket:
                self.packet_count_persistent += 1
                self.byte_count_persistent += pkt['header_len'] + pkt['payload_len']
            self.bucket.clear()

    def start_update(self):
        """
        Use a condition variable to mediate access to bucket state as it is
        being updated.

        Why condition variables and not locks? The main reason is that the state
        update doesn't happen in just a single function call here, since the
        runtime processes the classifier rule by rule and buckets may be touched
        in arbitrary order depending on the policy. They're not all updated in a
        single function call. In that case,

        (1) Holding locks *across* function calls seems dangerous and
        non-modular (in my opinion), since we need to be aware of this across a
        large function, and acquiring locks in different orders at different
        points in the code can result in tricky deadlocks (there is another lock
        involved in protecting bucket updates in runtime).

        (2) The "with" semantics in python is clean, and splitting that into
        lock.acquire() and lock.release() calls results in possibly replicated
        failure handling code that is boilerplate.

        """
        with self.in_update_cv:
            self.in_update = True
            self.matches = set([])
            self.runtime_stats_query_fun = None
            self.outstanding_switches = []

    def finish_update(self):
        with self.in_update_cv:
            self.in_update = False
            self.in_update_cv.notify_all()
        
    def add_match(self, m):
        """
        Add a match m to list of classifier rules to be queried for
        counts.
        """
        if not m in self.matches:
            self.matches.add(m)

    def add_pull_stats(self, fun):
        """
        Point to function that issues stats queries in the
        runtime.
        """
        if not self.runtime_stats_query_fun:
            self.runtime_stats_query_fun = fun

    def pull_stats(self):
        """Issue stats queries from the runtime"""
        queries_issued = False
        with self.in_update_cv:
            while self.in_update: # ensure buckets not updated concurrently
                self.in_update_cv.wait()
            if not self.runtime_stats_query_fun is None:
                self.outstanding_switches = []
                queries_issued = True
                self.runtime_stats_query_fun()
        # If no queries were issued, then no matches, so just call userland
        # registered callback routines
        if not queries_issued:
            self.packet_count = self.packet_count_persistent
            self.byte_count = self.byte_count_persistent
            for f in self.callbacks:
                f([self.packet_count, self.byte_count])

    def add_outstanding_switch_query(self,switch):
        self.outstanding_switches.append(switch)

    def handle_flow_stats_reply(self,switch,flow_stats):
        """
        Given a flow_stats_reply from switch s, collect only those
        counts which are relevant to this bucket.

        Very simple processing for now: just collect all packet and
        byte counts from rules that have a match that is in the set of
        matches this bucket is interested in.
        """
        def stat_in_bucket(flow_stat, s):
            table_match = match(f['match']).intersect(match(switch=s))
            network_match = match(f['match'])
            if table_match in self.matches or network_match in self.matches:
                return True
            return False

        with self.in_update_cv:
            while self.in_update:
                self.in_update_cv.wait()
            self.packet_count = self.packet_count_persistent
            self.byte_count = self.byte_count_persistent
            if switch in self.outstanding_switches:
                for f in flow_stats:
                    if 'match' in f:
                        if stat_in_bucket(f, switch):
                            self.packet_count += f['packet_count']
                            self.byte_count   += f['byte_count']
                self.outstanding_switches.remove(switch)
        # If have all necessary data, call user-land registered callbacks
        if not self.outstanding_switches:
            for f in self.callbacks:
                f([self.packet_count, self.byte_count])

    def __eq__(self, other):
        # TODO: if buckets eventually have names, equality should
        # be on names.
        return isinstance(other, CountBucket)

################################################################################
# Combinator Policies                                                          #
################################################################################

class CombinatorPolicy(Policy):
    """
    Abstract class for policy combinators.

    :param policies: the policies to be combined.
    :type policies: list Policy
    """
    ### init : List Policy -> unit
    def __init__(self, policies=[]):
        self.policies = list(policies)
        super(CombinatorPolicy,self).__init__()

    def __repr__(self):
        return "%s:\n%s" % (self.name(),util.repr_plus(self.policies))

    def __eq__(self, other):
        return ( self.__class__ == other.__class__
           and   self.policies == other.policies )


class negate(CombinatorPolicy,Filter):
    """
    Combinator that negates the input policy.

    :param policies: the policies to be negated.
    :type policies: list Filter
    """
    def eval(self, pkt):
        """
        evaluate this policy on a single packet

        :param pkt: the packet on which to be evaluated
        :type pkt: Packet
        :rtype: set Packet
        """
        if self.policies[0].eval(pkt):
            return set()
        else:
            return {pkt}

    def compile(self):
        """
        Produce a Classifier for this policy

        :rtype: Classifier
        """
        inner_classifier = self.policies[0].compile()
        classifier = Classifier([])
        for r in inner_classifier.rules:
            action = r.actions[0]
            if action == identity:
                classifier.rules.append(Rule(r.match,[drop]))
            elif action == drop:
                classifier.rules.append(Rule(r.match,[identity]))
            else:
                raise TypeError  # TODO MAKE A CompileError TYPE
        return classifier


class parallel(CombinatorPolicy):
    """
    Combinator for several policies in parallel.

    :param policies: the policies to be combined.
    :type policies: list Policy
    """
    def __new__(self, policies=[]):
        # Hackety hack.
        if len(policies) == 0:
            return drop
        else:
            rv = super(parallel, self).__new__(parallel, policies)
            rv.__init__(policies)
            return rv

    def __init__(self, policies=[]):
        if len(policies) == 0:
            raise TypeError
        super(parallel, self).__init__(policies)

    def __add__(self, pol):
        if isinstance(pol,parallel):
            return parallel(self.policies + pol.policies)
        else:
            return parallel(self.policies + [pol])

    def eval(self, pkt):
        """
        evaluates to the set union of the evaluation
        of self.policies on pkt

        :param pkt: the packet on which to be evaluated
        :type pkt: Packet
        :rtype: set Packet
        """
        output = set()
        for policy in self.policies:
            output |= policy.eval(pkt)
        return output

    def compile(self):
        """
        Produce a Classifier for this policy

        :rtype: Classifier
        """
        if len(self.policies) == 0:  # EMPTY PARALLEL IS A DROP
            return drop.compile()
        classifiers = map(lambda p: p.compile(), self.policies)
        return reduce(lambda acc, c: acc + c, classifiers)


class union(parallel,Filter):
    """
    Combinator for several filter policies in parallel.

    :param policies: the policies to be combined.
    :type policies: list Filter
    """
    def __new__(self, policies=[]):
        # Hackety hack.
        if len(policies) == 0:
            return drop
        else:
            rv = super(parallel, self).__new__(union, policies)
            rv.__init__(policies)
            return rv

    def __init__(self, policies=[]):
        if len(policies) == 0:
            raise TypeError
        super(union, self).__init__(policies)

    ### or : Filter -> Filter
    def __or__(self, pol):
        if isinstance(pol,union):
            return union(self.policies + pol.policies)
        elif isinstance(pol,Filter):
            return union(self.policies + [pol])
        else:
            raise TypeError


class sequential(CombinatorPolicy):
    """
    Combinator for several policies in sequence.

    :param policies: the policies to be combined.
    :type policies: list Policy
    """
    def __new__(self, policies=[]):
        # Hackety hack.
        if len(policies) == 0:
            return identity
        else:
            rv = super(sequential, self).__new__(sequential, policies)
            rv.__init__(policies)
            return rv

    def __init__(self, policies=[]):
        if len(policies) == 0:
            raise TypeError
        super(sequential, self).__init__(policies)

    def __rshift__(self, pol):
        if isinstance(pol,sequential):
            return sequential(self.policies + pol.policies)
        else:
            return sequential(self.policies + [pol])

    def eval(self, pkt):
        """
        evaluates to the set union of each policy in 
        self.policies on each packet in the output of the 
        previous.  The first policy in self.policies is 
        evaled on pkt.

        :param pkt: the packet on which to be evaluated
        :type pkt: Packet
        :rtype: set Packet
        """
        prev_output = {pkt}
        output = prev_output
        for policy in self.policies:
            if not prev_output:
                return set()
            if policy == identity:
                continue
            if policy == drop:
                return set()
            output = set()
            for p in prev_output:
                output |= policy.eval(p)
            prev_output = output
        return output

    def compile(self):
        """
        Produce a Classifier for this policy

        :rtype: Classifier
        """
        assert(len(self.policies) > 0)
        classifiers = map(lambda p: p.compile(),self.policies)
        for c in classifiers:
            assert(c is not None)
        return reduce(lambda acc, c: acc >> c, classifiers)


class intersection(sequential,Filter):
    """
    Combinator for several filter policies in sequence.

    :param policies: the policies to be combined.
    :type policies: list Filter
    """
    def __new__(self, policies=[]):
        # Hackety hack.
        if len(policies) == 0:
            return identity
        else:
            rv = super(sequential, self).__new__(intersection, policies)
            rv.__init__(policies)
            return rv

    def __init__(self, policies=[]):
        if len(policies) == 0:
            raise TypeError
        super(intersection, self).__init__(policies)

    ### and : Filter -> Filter
    def __and__(self, pol):
        if isinstance(pol,intersection):
            return intersection(self.policies + pol.policies)
        elif isinstance(pol,Filter):
            return intersection(self.policies + [pol])
        else:
            raise TypeError


################################################################################
# Derived Policies                                                             #
################################################################################

class DerivedPolicy(Policy):
    """
    Abstract class for a policy derived from another policy.

    :param policy: the internal policy (assigned to self.policy)
    :type policy: Policy
    """
    def __init__(self, policy=identity):
        self.policy = policy
        super(DerivedPolicy,self).__init__()

    def eval(self, pkt):
        """
        evaluates to the output of self.policy.

        :param pkt: the packet on which to be evaluated
        :type pkt: Packet
        :rtype: set Packet
        """
        return self.policy.eval(pkt)

    def compile(self):
        """
        Produce a Classifier for this policy

        :rtype: Classifier
        """
        return self.policy.compile()

    def __repr__(self):
        return "[DerivedPolicy]\n%s" % repr(self.policy)

    def __eq__(self, other):
        return ( self.__class__ == other.__class__
           and ( self.policy == other.policy ) )


class difference(DerivedPolicy,Filter):
    """
    The difference between two filter policies..

    :param f1: the minuend
    :type f1: Filter
    :param f2: the subtrahend
    :type f2: Filter
    """
    def __init__(self, f1, f2):
       self.f1 = f1
       self.f2 = f2
       super(difference,self).__init__(~f2 & f1)

    def __repr__(self):
        return "difference:\n%s" % util.repr_plus([self.f1,self.f2])


class if_(DerivedPolicy):
    """
    if pred holds, t_branch, otherwise f_branch.

    :param pred: the predicate
    :type pred: Filter
    :param t_branch: the true branch policy
    :type pred: Policy
    :param f_branch: the false branch policy
    :type pred: Policy
    """
    def __init__(self, pred, t_branch, f_branch=identity):
        self.pred = pred
        self.t_branch = t_branch
        self.f_branch = f_branch
        super(if_,self).__init__((self.pred >> self.t_branch) +
                                 ((~self.pred) >> self.f_branch))

    def eval(self, pkt):
        if self.pred.eval(pkt):
            return self.t_branch.eval(pkt)
        else:
            return self.f_branch.eval(pkt)

    def __repr__(self):
        return "if\n%s\nthen\n%s\nelse\n%s" % (util.repr_plus([self.pred]),
                                               util.repr_plus([self.t_branch]),
                                               util.repr_plus([self.f_branch]))


class fwd(DerivedPolicy):
    """
    fwd out a specified port.

    :param outport: the port on which to forward.
    :type outport: int
    """
    def __init__(self, outport):
        self.outport = outport
        super(fwd,self).__init__(modify(outport=self.outport))

    def __repr__(self):
        return "fwd %s" % self.outport


class xfwd(DerivedPolicy):
    """
    fwd out a specified port, unless the packet came in on that same port.
    (Semantically equivalent to OpenFlow's forward action

    :param outport: the port on which to forward.
    :type outport: int
    """
    def __init__(self, outport):
        self.outport = outport
        super(xfwd,self).__init__((~match(inport=outport)) >> fwd(outport))

    def __repr__(self):
        return "xfwd %s" % self.outport


class link(DerivedPolicy):
    """
    Topology link from a source switch and outport to a dest switch and inport

    :param outswitch: the source switch.
    :type outswitch: int
    :param outport: the port on the source switch we forward out.
    :type outport: int
    :param inswitch: the destination switch.
    :type inswitch: int
    :param inport: the port on the dest switch we receive the packet from.
    :type inport: int
    """
    def __init__(self, outswitch, outport, inswitch, inport):
        self.outswitch = outswitch
        self.outport = outport
        self.inswitch = inswitch
        self.inport = inport
        super(link, self).__init__(match(switch = self.outswitch, outport = self.outport)
            >> modify(switch = self.inswitch, inport = self.inport, outport = None))

    def __repr__(self):
        return "link from %s:%s to %s:%s" % (self.outswitch, self.outport,
                                             self.inswitch, self.inport)

################################################################################
# Dynamic Policies                                                             #
################################################################################

class DynamicPolicy(DerivedPolicy):
    """
    Abstact class for dynamic policies.
    The behavior of a dynamic policy changes each time self.policy is reassigned.
    """
    ### init : unit -> unit
    def __init__(self,policy=drop):
        self._policy = policy
        self.notify = None
        super(DerivedPolicy,self).__init__()

    def set_network(self, network):
        pass

    def attach(self,notify):
        self.notify = notify

    def detach(self):
        self.notify = None

    def changed(self):
        if self.notify:
            self.notify()

    @property
    def policy(self):
        return self._policy

    @policy.setter
    def policy(self, policy):
        prev_policy = self._policy
        self._policy = policy
        self.changed()

    def __repr__(self):
        return "[DynamicPolicy]\n%s" % repr(self.policy)


class DynamicFilter(DynamicPolicy,Filter):
    """
    Abstact class for dynamic filter policies.
    The behavior of a dynamic filter policy changes each time self.policy is reassigned.
    """
    pass


class flood(DynamicPolicy):
    """
    Policy that floods packets on a minimum spanning tree, recalculated
    every time the network is updated (set_network).
    """
    def __init__(self):
        self.mst = None
        super(flood,self).__init__()

    def set_network(self, network):
        changed = False
        if not network is None:
            updated_mst = Topology.minimum_spanning_tree(network.topology)
            if not self.mst is None:
                if self.mst != updated_mst:
                    self.mst = updated_mst
                    changed = True
            else:
                self.mst = updated_mst
                changed = True
        if changed:
            self.policy = parallel([
                    match(switch=switch) >>
                        parallel(map(xfwd,attrs['ports'].keys()))
                    for switch,attrs in self.mst.nodes(data=True)])

    def __repr__(self):
        try:
            return "flood on:\n%s" % self.mst
        except:
            return "flood"


class ingress_network(DynamicFilter):
    """
    Returns True if a packet is located at a (switch,inport) pair entering
    the network, False otherwise.
    """
    def __init__(self):
        self.egresses = None
        super(ingress_network,self).__init__()

    def set_network(self, network):
        updated_egresses = network.topology.egress_locations()
        if not self.egresses == updated_egresses:
            self.egresses = updated_egresses
            self.policy = parallel([match(switch=l.switch,
                                       inport=l.port_no)
                                 for l in self.egresses])

    def __repr__(self):
        return "ingress_network"


class egress_network(DynamicFilter):
    """
    Returns True if a packet is located at a (switch,outport) pair leaving
    the network, False otherwise.
    """
    def __init__(self):
        self.egresses = None
        super(egress_network,self).__init__()

    def set_network(self, network):
        updated_egresses = network.topology.egress_locations()
        if not self.egresses == updated_egresses:
            self.egresses = updated_egresses
            self.policy = parallel([match(switch=l.switch,
                                       outport=l.port_no)
                                 for l in self.egresses])

    def __repr__(self):
        return "egress_network"


###############################################################################
# Class hierarchy syntax tree traversal

def ast_fold(fun, acc, policy):
    import pyretic.lib.query as query
    if (  policy == identity or
          policy == drop or
          isinstance(policy,match) or
          isinstance(policy,modify) or
          policy == Controller or
          isinstance(policy,Query)):
        return fun(acc,policy)
    elif (isinstance(policy,negate) or
          isinstance(policy,parallel) or
          isinstance(policy,union) or
          isinstance(policy,sequential) or
          isinstance(policy,intersection)):
        acc = fun(acc,policy)
        for sub_policy in policy.policies:
            acc = ast_fold(fun,acc,sub_policy)
        return acc
    elif (isinstance(policy,difference) or
          isinstance(policy,if_) or
          isinstance(policy,fwd) or
          isinstance(policy,xfwd) or
          isinstance(policy,DynamicPolicy) or
          isinstance(policy,query.packets)):
        acc = fun(acc,policy)
        return ast_fold(fun,acc,policy.policy)
    else:
        raise NotImplementedError
    
def add_dynamic_sub_pols(acc, policy):
    if isinstance(policy,DynamicPolicy):
        return acc | {policy}
    else:
        return acc

def add_query_sub_pols(acc, policy):
    from pyretic.lib.query import packets
    if ( isinstance(policy,Query) or
         isinstance(policy,packets)) : ### TODO remove this hack once packets is refactored 
        return add | {policy}
    else:
        return acc

def queries_in_eval(acc, policy):
    res,pkts = acc
    if policy == drop:
        acc = (res,set())
    elif policy == identity:
        pass
    elif (isinstance(policy,match) or 
          isinstance(policy,modify) or 
          isinstance(policy,negate)):
        new_pkts = set()
        for pkt in pkts:
            new_pkts |= policy.eval(pkt)
        acc = (res,new_pkts)
    elif isinstance(policy,Query):
        acc = (res | {policy}, set())
    elif isinstance(policy,DerivedPolicy):
        acc = queries_in_eval(acc,policy.policy)
    elif isinstance(policy,parallel):
        parallel_res = set()
        parallel_pkts = set()
        for sub_pol in policy.policies:
            new_res,new_pkts = queries_in_eval((res,pkts),sub_pol)
            parallel_res |= new_res
            parallel_pkts |= new_pkts
        acc = (parallel_res,parallel_pkts)
    elif isinstance(policy,sequential):
        for sub_pol in policy.policies:
            acc = queries_in_eval(acc,sub_pol)
            if not acc[1]:
                break
    return acc


###############################################################################
# Classifiers
# an intermediate representation for proactive compilation.

class Rule(object):
    """
    A rule contains a filter and the parallel composition of zero or more
    Pyretic actions.
    """

    # Matches m should be of the match class.  Actions acts should be a list of
    # either modify, identity, or drop policies.
    def __init__(self,m,acts):
        self.match = m
        self.actions = acts

    def __str__(self):
        return str(self.match) + '\n  -> ' + str(self.actions)

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        """Based on syntactic equality of policies."""
        return ( id(self) == id(other)
            or ( self.match == other.match
                 and self.actions == other.actions ) )

    def __ne__(self, other):
        """Based on syntactic equality of policies."""
        return not (self == other)

    def eval(self, in_pkt):
        """
        If this rule matches the packet, then return the union of the sets
        of packets produced by the actions.  Otherwise, return None.
        """
        filtered_pkt = self.match.eval(in_pkt)
        if len(filtered_pkt) == 0:
            return None
        rv = set()
        for pkt in filtered_pkt:
            for act in self.actions:
                rv |= act.eval(pkt)
        return rv


class Classifier(object):
    """
    A classifier contains a list of rules, where the order of the list implies
    the relative priorities of the rules.  Semantically, classifiers are
    functions from packets to sets of packets, similar to OpenFlow flow
    tables.
    """

    def __init__(self, new_rules=[]):
        import types
        if isinstance(new_rules, types.GeneratorType):
            self.rules = [r for r in new_rules]
        elif isinstance(new_rules,list):
            self.rules = new_rules
        else:
            raise TypeError

    def __len__(self):
        return len(self.rules)

    def __str__(self):
        return '\n '.join(map(str,self.rules))

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        """Based on syntactic equality of policies."""
        return ( id(self) == id(other)
            or ( self.rules == other.rules ) )

    def __ne__(self, other):
        """Based on syntactic equality of policies."""
        return not (self == other)

    def __add__(self,c2):
        c1 = self
        if c2 is None:
            return None
        c = Classifier([])
        # TODO (cole): make classifiers iterable
        for r1 in c1.rules:
            for r2 in c2.rules:
                intersection = r1.match.intersect(r2.match)
                if intersection != drop:
                    # TODO (josh) logic for detecting when sets of actions can't be combined
                    # e.g., [modify(dstip='10.0.0.1'),fwd(1)] + [modify(srcip='10.0.0.2'),fwd(2)]
                    actions = r1.actions + r2.actions
                    actions = filter(lambda a: a != drop,actions)
                    if len(actions) == 0:
                        actions = [drop]
                    c.rules.append(Rule(intersection, actions))
        for r1 in c1.rules:
            c.rules.append(r1)
        for r2 in c2.rules:
            c.rules.append(r2)
        return c.optimize()

    # Helper function for rshift: given a test b and an action p, return a test
    # b' such that p >> b == b' >> p.
    def _commute_test(self, act, pkts):
        while isinstance(act, DerivedPolicy):
            act = act.policy
        if act == identity:
            return pkts
        elif act == drop:
            return drop
        elif act == Controller or isinstance(act, CountBucket):
            return identity
        elif isinstance(act, modify):
            new_match_dict = {}
            if pkts == identity:
                return identity
            elif pkts == drop:
                return drop
            for f, v in pkts.map.iteritems():
                if f in act.map and act.map[f] == v:
                    continue
                elif f in act.map and act.map[f] != v:
                    return drop
                else:
                    new_match_dict[f] = v
            if len(new_match_dict) == 0:
                return identity
            return match(**new_match_dict)
        else:
            # TODO (cole) use compile error.
            # TODO (cole) what actions are allowable?
            raise TypeError

    # Helper function for rshift: sequentially compose actions.  a1 must be a
    # single action.  Returns a list of actions.
    def _sequence_actions(self, a1, as2):
        while isinstance(a1, DerivedPolicy):
            a1 = a1.policy
        # TODO: be uniform about returning copied or modified objects.
        new_actions = []
        if a1 == drop:
            return [drop]
        elif a1 == identity:
            return as2
        elif a1 == Controller or isinstance(a1, CountBucket):
            return [a1]
        elif isinstance(a1, modify):
            for a2 in as2:
                while isinstance(a2, DerivedPolicy):
                    a2 = a2.policy
                new_a1 = modify(**a1.map.copy())
                if a2 == drop:
                    new_actions.append(drop)
                elif a2 == Controller or isinstance(a2, CountBucket): 
                    new_actions.append(a2)
                elif a2 == identity:
                    new_actions.append(new_a1)
                elif isinstance(a2, modify):
                    new_a1.map.update(a2.map)
                    new_actions.append(new_a1)
                elif isinstance(a2, fwd):
                    new_a1.map['outport'] = a2.outport
                    new_actions.append(new_a1)
                else:
                    raise TypeError
            return new_actions
        else:
            raise TypeError

    # Returns a classifier.
    def _sequence_action_classifier(self, act, c):
        # TODO (cole): make classifiers easier to use w.r.t. adding/removing
        # rules.
        if len(c.rules) == 0:
            return Classifier([Rule(identity, [drop])])
        new_rules = []
        for rule in c.rules:
            pkts = self._commute_test(act, rule.match)
            if pkts == identity:
                acts = self._sequence_actions(act, rule.actions)
                new_rules += [Rule(identity, acts)]
                break
            elif pkts == drop:
                continue
            else:
                acts = self._sequence_actions(act, rule.actions)
                new_rules += [Rule(pkts, acts)]
        if new_rules == []:
            return Classifier([Rule(identity, [drop])])
        else:
            return Classifier(new_rules)
                
    def _sequence_actions_classifier(self, acts, c):
        empty_classifier = Classifier([Rule(identity, [drop])])
        if acts == []:
            # Treat the empty list of actions as drop.
            return empty_classifier
        acc = empty_classifier
        for act in acts:
            acc = acc + self._sequence_action_classifier(act, c)
        return acc

    def _sequence_rule_classifier(self, r, c):
        c2 = self._sequence_actions_classifier(r.actions, c)
        for rule in c2.rules:
            rule.match = rule.match.intersect(r.match)
        c2.rules = [r2 for r2 in c2.rules if r2.match != drop]
        return c2.optimize()

    def __rshift__(self, c2):
        new_rules = []
        for rule in self.rules:
            c3 = self._sequence_rule_classifier(rule, c2)
            new_rules = new_rules + c3.rules
        rv = Classifier(new_rules)
        return rv.optimize()

    def optimize(self):
        return self.remove_shadowed_cover_single()

    def remove_shadowed_exact_single(self):
        # Eliminate every rule exactly matched by some higher priority rule
        opt_c = Classifier([])
        for r in self.rules:
            if not reduce(lambda acc, new_r: acc or
                          new_r.match == r.match,
                          opt_c.rules,
                          False):
                opt_c.rules.append(r)
        return opt_c

    def remove_shadowed_cover_single(self):
        # Eliminate every rule completely covered by some higher priority rule
        opt_c = Classifier([])
        for r in self.rules:
            if not reduce(lambda acc, new_r: acc or
                          new_r.match.covers(r.match),
                          opt_c.rules,
                          False):
                opt_c.rules.append(r)
        return opt_c

    def eval(self, in_pkt):
        """
        Evaluate against each rule in the classifier, starting with the
        highest priority.  Return the set of packets resulting from applying
        the actions of the first rule that matches.
        """
        for rule in self.rules:
            pkts = rule.eval(in_pkt)
            if pkts is not None:
                return pkts
        raise TypeError('Classifier is not total.')


###############################################################################
# Simplifies a given policy for traceback.
# This means that queries, Controllers, etc. will be treated as drops! Don't
# use this as is to simplify policies for "normal" use (e.g. compilation) or
# all sorts of things will be broken.
###############################################################################
def simplify_tb(policy):

    # Controller or Query is really just drop for traceback.
    if policy is Controller or isinstance(policy, Query):
        return drop

    elif isinstance(policy, sequential):
        # If there was a drop/Query/Controller in there, that's definitely a drop.
        if drop in policy.policies or any(p is Controller or isinstance(p, Query) for p in policy.policies):
          return drop
        
        # Simplify each term, ignoring all identities.
        policies = [simplify_tb(p) for p in policy.policies if p is not identity]
        
        # Remove parens on any nested sequentials, since a >> (b >> c) = a >> b >> c
        flat_policies = []
        for i in range(len(policies)):
            if isinstance(policies[i], sequential):
                flat_policies.extend(policies[i].policies)
            else:
                flat_policies.append(policies[i])
        policies = flat_policies

        # If there's only one policy after doing all that, just return that
        if len(policies) is 1:
            return policies[0]
        
        # Iteratively simplify each pair until the end; backtrack and consolidate after each change.
        i = 0
        while i < len(policies) - 1:
            simplified = simplify_seq_pair(policies[i:i+2])
            if simplified is drop:
                return drop
            elif simplified == sequential(policies[i:i+2]):
                i += 1
            else:
                del policies[i:i+2]
                policies.insert(i, simplified)
                i = 0
        return sequential(policies)

    elif isinstance(policy, parallel):
        # Simplify each term, ignoring all identities.
        policies = [simplify_tb(p) for p in policy.policies]
        if identity in policies:
            return identity
        return parallel(policies)

    elif isinstance(policy, negate):
        return policy #TODO

      # Apply back policy algorithm to the underlying policy of Derived policies
    elif isinstance(policy, DerivedPolicy):
        return simplify_tb(policy.policy)

    # We can't simplify drop / identity / match / modify
    else:
        return policy

# Helper function for simplify_tb that simplifies a sequential pair of policies.
# 'pair' is a list containing two policies. Returns the (maybe simplified) policy.
def simplify_seq_pair(pair):

    if isinstance(pair[0], match):
        
        # Two matches in a row. Can either merge or simplify to drop.
        if isinstance(pair[1], match):
            dup_keys = list(set(pair[0].map.keys()) & set(pair[1].map.keys()))
            for key in dup_keys:
                if pair[0].map[key] != pair[1].map[key]: # TODO: deal with IP prefixing
                    return drop
            pair[0].map = pair[0].map.update(pair[1].map)
            return pair[0]
        else:
            return sequential(pair)

    elif isinstance(pair[0], modify):
        
        # Two modifys in a row; always merge.
        if isinstance(pair[1], modify):
            pair[0].map = pair[0].map.update(pair[1].map)
            return pair[0]
        
        # modify >> match. Simplifies to drop if any fields match with different values.
        elif isinstance(pair[1], match):
            return sequential(pair) # TODO
        else:
            return sequential(pair)

    elif isinstance(pair[0], sum_modify):
        
        # Sum modify followed by match. Try to resolve some ambiguity.
        if isinstance(pair[1], match):
            match_keys = list(set(pair[0].fields.keys()) & set(pair[1].map.keys()))
            # Can't really simplify anything if all keys are different.
            if len(match_keys) is 0:
                return sequential(pair)
            # Merge match fields into modify fields and simplify!
            mcopy = match(pair[1].map) # Copy match first, since otherwise negations get messed up...
            for key in match_keys:
                pair[0].restrict(key, match({key:mcopy.map[key]}))
                # If there are any resultant drops, the whole sequential policy is a drop.
                if pair[0].fields[key] is drop:
                    return drop
                mcopy.map = mcopy.map.remove([key]) # Remove the entry from the match
            simplified = sum_to_modify(pair[0])
            # if anything left in the match, append it to the simplified sum_modify
            if len(mcopy.map) > 0:
                simplified = simplified >> mcopy
            return simplified
        
        # Sum modify followed by modify. Kill any fields in sum_modify shadowed by modify.
        if isinstance(pair[1], modify):
            shadowed_keys = list(set(pair[0].fields.keys()) & set(pair[1].map.keys()))
            if len(shadowed_keys) is 0:
                return sequential(pair)
            for key in shadowed_keys:
                pair[0].fields.pop(key)
            if len(pair[0].fields) is 0:
                return pair[1]
            else:
                return pair[0] >> pair[1]
        else:
            return sequential(pair)
    
    else:
        return sequential(pair)

# Helper function for taking a sum_modify policy sm and returning the sequential
# composition consisting of any modifies that can be pulled out followed by the
# remainder of the sum_modify. We pull out any modifies whose field policies eval
# to a "few" possibilities (e.g. match with no negates after simplification)
def sum_to_modify(sm):
    mod = None
    for key in sm.fields.copy():
        policy = sm.fields[key]
        if policy is identity:
            continue
        # Simplify if match
        elif isinstance(policy, match):
            if mod:
                mod.map.update(policy.map)
            else:
                mod = modify(policy.map)
            sm.fields.pop(key)
        # Should never see drop.
        elif policy is drop:
            raise RuntimeError("Something went wrong; sum_modify should never have a drop for a field.")
        # TODO handle parallel, other cases
    if mod:
        if len(sm.fields) is 0:
            return mod
        else:
            return mod >> sm
    else:
        return sm