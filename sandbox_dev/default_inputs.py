#!/usr/local/bin/python
# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Does specifying a . in an input file result in the parameter retaining
its default value, mimicking the behavior of AMPL?

The answer is yes, it does.
"""

import os
from pyomo.environ import *

m = AbstractModel()
m.S = Set(initialize=[1, 2, 3])
m.p = Param(m.S, default={1: 'a', 2: 'b', 3: 'c'})
i_d = m.create()

print "Values from initial defaults should be a, b, c:\n"
print [i_d.p[s] for s in i_d.S]

# Write a test data file.
# Overwrite default value for index 1
# Specify default value for index 2 with .
# Don't specify anything for 3, which should yield the default value.
path = 'foo.tab'
with open(path, 'w') as f:
    f.write("S\tp\n")
    f.write("1\t10\n")
    f.write("2\t.\n")

dp = DataPortal(model=m)
dp.load(filename=path, param=(m.p))
i_f = m.create(dp)
print "Values after reading from file should be 10, b, c:\n"
print [i_f.p[s] for s in i_f.S]

os.remove(path)
