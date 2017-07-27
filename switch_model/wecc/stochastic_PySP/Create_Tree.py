#!/usr/bin/env python
# Copyright 2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.
# Renewable and Appropriate Energy Laboratory, UC Berkeley.

"""

Creates inputs for all scenarios and structure for stochastic SWITCH WECC.

"""

import os, argparse, switch_model.get_inputs, subprocess
#from distutils.core import setup

parser.add_argument(
	'-path0', type=str, default='inputs', metavar='inputsdir',
	help='Directory where the inputs from the root will be built')
parser.add_argument(
	'-path1', type=str, default='inputs1', metavar='inputsdir',
	help='Directory where the inputs from scenario 1 will be built')
parser.add_argument(
	'-path2', type=str, default='inputs2', metavar='inputsdir',
	help='Directory where the inputs from scenario 2 will be built')	
parser.add_argument(
	'-path3', type=str, default='inputs3', metavar='inputsdir',
	help='Directory where the inputs from scenario 3 will be built')
parser.add_argument(
	'-s0', type=int, required=True, metavar='scenario_id1',
	help='Scenario ID for root of the simulation')
parser.add_argument(
	'-s1', type=int, required=True, metavar='scenario_id1',
	help='Scenario 1 ID for the simulation')
parser.add_argument(
	'-s2', type=int, required=True, metavar='scenario_id2',
	help='Scenario 2 ID for the simulation')
parser.add_argument(
	'-s3', type=int, required=True, metavar='scenario_id3',
	help='Scenario 3 ID for the simulation')

args = parser.parse_args()
        
# getting inputs for scenarios:    
switch_model.get_inputs -s arg.s0 -i arg.path0
switch_model.get_inputs -s arg.s1 -i arg.path1
switch_model.get_inputs -s arg.s2 -i arg.path2
switch_model.get_inputs -s arg.s3 -i arg.path3

subprocess.call("PySPInputGenerator.py", shell=True)






