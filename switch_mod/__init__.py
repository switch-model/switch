# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
This package defines the Switch model for Pyomo.

core_modules is a list of required modules which may be used in the future
for error checking.

An additional module is required to describe fuel costs - either
fuel_cost which specifies a simple flat fuel cost that can vary by load
zone and period, or fuel_markets which specifies a tiered supply curve.

Also, an additional module is required to constrain project dispatch -
either operations.no_commit or operations.unitcommit.

Most applications of Switch will also benefit from optional modules such as 
transmission, local_td, reserves, etc.
"""
__version__='2.0.0b1'
core_modules = [
    'switch_mod.timescales',
    'switch_mod.financials',
    'switch_mod.balancing.load_zones',
    'switch_mod.energy_sources.properties',
    'switch_mod.generators.core',
    'switch_mod.reporting']
