# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines transmission build-outs.
"""

import os
from pyomo.environ import *
from switch_model.financials import capital_recovery_factor as crf
import pandas as pd

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials'

def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe bulk
    transmission of an electric grid. This includes parameters, build
    decisions and constraints. Unless otherwise stated, all power
    capacity is specified in units of MW and all sets and parameters are
    mandatory.

    TRANSMISSION_LINES is the complete set of transmission pathways
    connecting load zones. Each member of this set is a one dimensional
    identifier such as "A-B". This set has no regard for directionality
    of transmission lines and will generate an error if you specify two
    lines that move in opposite directions such as (A to B) and (B to
    A). Another derived set - TRANS_LINES_DIRECTIONAL - stores
    directional information. Transmission may be abbreviated as trans or
    tx in parameter names or indexes.

    trans_lz1[tx] and trans_lz2[tx] specify the load zones at either end
    of a transmission line. The order of 1 and 2 is unimportant, but you
    are encouraged to be consistent to simplify merging information back
    into external databases.

    trans_dbid[tx in TRANSMISSION_LINES] is an external database
    identifier for each transmission line. This is an optional parameter
    than defaults to the identifier of the transmission line.

    trans_length_km[tx in TRANSMISSION_LINES] is the length of each
    transmission line in kilometers.

    trans_efficiency[tx in TRANSMISSION_LINES] is the proportion of
    energy sent down a line that is delivered. If 2 percent of energy
    sent down a line is lost, this value would be set to 0.98.

    trans_new_build_allowed[tx in TRANSMISSION_LINES] is a binary value
    indicating whether new transmission build-outs are allowed along a
    transmission line. This optional parameter defaults to True.

    BLD_YRS_FOR_TX is the set of transmission lines and years in
    which they have been or could be built. This set includes past and
    potential future builds. All future builds must come online in the
    first year of an investment period. This set is composed of two
    elements with members: (tx, build_year). For existing transmission
    where the build years are not known, build_year is set to 'Legacy'.

    BLD_YRS_FOR_EXISTING_TX is a subset of BLD_YRS_FOR_TX that lists
    builds that happened before the first investment period. For most
    datasets the build year is unknown, so is it always set to 'Legacy'.

    existing_trans_cap[tx in TRANSMISSION_LINES] is a parameter that
    describes how many MW of capacity has been installed before the
    start of the study.

    NEW_TRANS_BLD_YRS is a subset of BLD_YRS_FOR_TX that describes
    potential builds.

    BuildTx[(tx, bld_yr) in BLD_YRS_FOR_TX] is a decision variable
    that describes the transfer capacity in MW installed on a corridor
    in a given build year. For existing builds, this variable is locked
    to the existing capacity.

    TxCapacityNameplate[(tx, bld_yr) in BLD_YRS_FOR_TX] is an expression
    that returns the total nameplate transfer capacity of a transmission
    line in a given period. This is the sum of existing and newly-build
    capacity.

    trans_derating_factor[tx in TRANSMISSION_LINES] is an overall
    derating factor for each transmission line that can reflect forced
    outage rates, stability or contingency limitations. This parameter
    is optional and defaults to 1. This parameter should be in the
    range of 0 to 1, being 0 a value that disables the line completely.

    TxCapacityNameplateAvailable[(tx, bld_yr) in BLD_YRS_FOR_TX] is an
    expression that returns the available transfer capacity of a
    transmission line in a given period, taking into account the
    nameplate capacity and derating factor.

    trans_terrain_multiplier[tx in TRANSMISSION_LINES] is
    a cost adjuster applied to each transmission line that reflects the
    additional costs that may be incurred for traversing that specific
    terrain. Crossing mountains or cities will be more expensive than
    crossing plains. This parameter is optional and defaults to 1. This
    parameter should be in the range of 0.5 to 3.

    trans_capital_cost_per_mw_km describes the generic costs of building
    new transmission in units of $BASE_YEAR per MW transfer capacity per
    km. This is optional and defaults to 1000.

    trans_lifetime_yrs is the number of years in which a capital
    construction loan for a new transmission line is repaid. This
    optional parameter defaults to 20 years based on 2009 WREZ
    transmission model transmission data. At the end of this time,
    we assume transmission lines will be rebuilt at the same cost.

    trans_fixed_om_fraction is describes the fixed Operations and
    Maintenance costs as a fraction of capital costs. This optional
    parameter defaults to 0.03 based on 2009 WREZ transmission model
    transmission data costs for existing transmission maintenance.

    trans_cost_hourly[tx TRANSMISSION_LINES] is the cost of building
    transmission lines in units of $BASE_YEAR / MW- transfer-capacity /
    hour. This derived parameter is based on the total annualized
    capital and fixed O&M costs, then divides that by hours per year to
    determine the portion of costs incurred hourly.

    DIRECTIONAL_TX is a derived set of directional paths that
    electricity can flow along transmission lines. Each element of this
    set is a two-dimensional entry that describes the origin and
    destination of the flow: (load_zone_from, load_zone_to). Every
    transmission line will generate two entries in this set. Members of
    this set are abbreviated as trans_d where possible, but may be
    abbreviated as tx in situations where brevity is important and it is
    unlikely to be confused with the overall transmission line.

    trans_d_line[trans_d] is the transmission line associated with this
    directional path.

    TX_BUILDS_IN_PERIOD[p in PERIODS] is an indexed set that
    describes which transmission builds will be operational in a given
    period. Currently, transmission lines are kept online indefinitely,
    with parts being replaced as they wear out.
    
    TX_BUILDS_IN_PERIOD[p] will return a subset of (tx, bld_yr)
    in BLD_YRS_FOR_TX.

    --- Delayed implementation ---

    is_dc_line ... Do I even need to implement this?

    --- NOTES ---

    The cost stream over time for transmission lines differs from the
    SWITCH-WECC model. The SWITCH-WECC model assumed new transmission
    had a financial lifetime of 20 years, which was the length of the
    loan term. During this time, fixed operations & maintenance costs
    were also incurred annually and these were estimated to be 3 percent
    of the initial capital costs. These fixed O&M costs were obtained
    from the 2009 WREZ transmission model transmission data costs for
    existing transmission maintenance .. most of those lines were old
    and their capital loans had been paid off, so the O&M were the costs
    of keeping them operational. SWITCH-WECC basically assumed the lines
    could be kept online indefinitely with that O&M budget, with
    components of the lines being replaced as needed. This payment
    schedule and lifetimes was assumed to hold for both existing and new
    lines. This made the annual costs change over time, which could
    create edge effects near the end of the study period. SWITCH-WECC
    had different cost assumptions for local T&D; capital expenses and
    fixed O&M expenses were rolled in together, and those were assumed
    to continue indefinitely. This basically assumed that local T&D would
    be replaced at the end of its financial lifetime.

    SWITCH-Pyomo treats all transmission and distribution (long-
    distance or local) the same. Any capacity that is built will be kept
    online indefinitely. At the end of its financial lifetime, existing
    capacity will be retired and rebuilt, so the annual cost of a line
    upgrade will remain constant in every future year.

    """

    mod.TRANSMISSION_LINES = Set()
    mod.trans_lz1 = Param(mod.TRANSMISSION_LINES, within=mod.LOAD_ZONES)
    mod.trans_lz2 = Param(mod.TRANSMISSION_LINES, within=mod.LOAD_ZONES)
    mod.min_data_check('TRANSMISSION_LINES', 'trans_lz1', 'trans_lz2')
    mod.trans_dbid = Param(mod.TRANSMISSION_LINES, default=lambda m, tx: tx)
    mod.trans_length_km = Param(mod.TRANSMISSION_LINES, within=PositiveReals)
    mod.trans_efficiency = Param(
        mod.TRANSMISSION_LINES,
        within=PositiveReals,
        validate=lambda m, val, tx: val <= 1)
    mod.BLD_YRS_FOR_EXISTING_TX = Set(
        dimen=2,
        initialize=lambda m: set(
            (tx, 'Legacy') for tx in m.TRANSMISSION_LINES))
    mod.existing_trans_cap = Param(
        mod.TRANSMISSION_LINES,
        within=NonNegativeReals)
    mod.min_data_check(
        'trans_length_km', 'trans_efficiency', 'BLD_YRS_FOR_EXISTING_TX',
        'existing_trans_cap')
    mod.trans_new_build_allowed = Param(
        mod.TRANSMISSION_LINES, within=Boolean, default=True)
    mod.NEW_TRANS_BLD_YRS = Set(
        dimen=2,
        initialize=mod.TRANSMISSION_LINES * mod.PERIODS,
        filter=lambda m, tx, p: m.trans_new_build_allowed[tx])
    mod.BLD_YRS_FOR_TX = Set(
        dimen=2,
        initialize=lambda m: m.BLD_YRS_FOR_EXISTING_TX | m.NEW_TRANS_BLD_YRS)
    mod.TX_BUILDS_IN_PERIOD = Set(
        mod.PERIODS,
        within=mod.BLD_YRS_FOR_TX,
        initialize=lambda m, p: set(
            (tx, bld_yr) for (tx, bld_yr) in m.BLD_YRS_FOR_TX
            if bld_yr == 'Legacy' or bld_yr <= p))

    def bounds_BuildTx(model, tx, bld_yr):
        if((tx, bld_yr) in model.BLD_YRS_FOR_EXISTING_TX):
            return (model.existing_trans_cap[tx],
                    model.existing_trans_cap[tx])
        else:
            return (0, None)
    mod.BuildTx = Var(
        mod.BLD_YRS_FOR_TX,
        within=NonNegativeReals,
        bounds=bounds_BuildTx)
    mod.TxCapacityNameplate = Expression(
        mod.TRANSMISSION_LINES, mod.PERIODS,
        rule=lambda m, tx, period: sum(
            m.BuildTx[tx, bld_yr]
            for (tx2, bld_yr) in m.BLD_YRS_FOR_TX
            if tx2 == tx and (bld_yr == 'Legacy' or bld_yr <= period)))
    mod.trans_derating_factor = Param(
        mod.TRANSMISSION_LINES,
        within=NonNegativeReals,
        default=1,
        validate=lambda m, val, tx: val <= 1)
    mod.TxCapacityNameplateAvailable = Expression(
        mod.TRANSMISSION_LINES, mod.PERIODS,
        rule=lambda m, tx, period: (
            m.TxCapacityNameplate[tx, period] * m.trans_derating_factor[tx]))
    mod.trans_terrain_multiplier = Param(
        mod.TRANSMISSION_LINES,
        within=Reals,
        default=1,
        validate=lambda m, val, tx: val >= 0.5 and val <= 3)
    mod.trans_capital_cost_per_mw_km = Param(
        within=PositiveReals,
        default=1000)
    mod.trans_lifetime_yrs = Param(
        within=PositiveReals,
        default=20)
    mod.trans_fixed_om_fraction = Param(
        within=PositiveReals,
        default=0.03)
    # Total annual fixed costs for building new transmission lines...
    # Multiply capital costs by capital recover factor to get annual
    # payments. Add annual fixed O&M that are expressed as a fraction of
    # overnight costs.
    mod.trans_cost_annual = Param(
        mod.TRANSMISSION_LINES,
        within=PositiveReals,
        initialize=lambda m, tx: (
            m.trans_capital_cost_per_mw_km * m.trans_terrain_multiplier[tx] *
            m.trans_length_km[tx] * (crf(m.interest_rate, m.trans_lifetime_yrs) +
                m.trans_fixed_om_fraction)))
    # An expression to summarize annual costs for the objective
    # function. Units should be total annual future costs in $base_year
    # real dollars. The objective function will convert these to
    # base_year Net Present Value in $base_year real dollars.
    mod.TxFixedCosts = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.BuildTx[tx, bld_yr] * m.trans_cost_annual[tx]
            for (tx, bld_yr) in m.TX_BUILDS_IN_PERIOD[p]))
    mod.Cost_Components_Per_Period.append('TxFixedCosts')

    def init_DIRECTIONAL_TX(model):
        tx_dir = set()
        for tx in model.TRANSMISSION_LINES:
            tx_dir.add((model.trans_lz1[tx], model.trans_lz2[tx]))
            tx_dir.add((model.trans_lz2[tx], model.trans_lz1[tx]))
        return tx_dir
    mod.DIRECTIONAL_TX = Set(
        dimen=2,
        initialize=init_DIRECTIONAL_TX)
    mod.TX_CONNECTIONS_TO_ZONE = Set(
        mod.LOAD_ZONES,
        initialize=lambda m, lz: set(
            z for z in m.LOAD_ZONES if (z,lz) in m.DIRECTIONAL_TX))

    def init_trans_d_line(m, zone_from, zone_to):
        for tx in m.TRANSMISSION_LINES:
            if((m.trans_lz1[tx] == zone_from and m.trans_lz2[tx] == zone_to) or
               (m.trans_lz2[tx] == zone_from and m.trans_lz1[tx] == zone_to)):
                return tx
    mod.trans_d_line = Param(
        mod.DIRECTIONAL_TX,
        within=mod.TRANSMISSION_LINES,
        initialize=init_trans_d_line)


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import data related to transmission builds. The following files are
    expected in the input directory:

    transmission_lines.tab
        TRANSMISSION_LINE, trans_lz1, trans_lz2, trans_length_km,
        trans_efficiency, existing_trans_cap

    The next files are optional. If they are not included or if any rows
    are missing, those parameters will be set to default values as
    described in documentation. If you only want to override some
    columns and not others in trans_optional_params, put a dot . in the
    columns that you don't want to override.

    trans_optional_params.tab
        TRANSMISSION_LINE, trans_dbid, trans_derating_factor,
        trans_terrain_multiplier, trans_new_build_allowed

    Note that the next file is formatted as .dat, not as .tab. The
    distribution_loss_rate parameter should only be inputted if the 
    local_td module is loaded in the simulation. If this parameter is
    specified a value in trans_params.dat and local_td is not included
    in the module list, then an error will be raised.

    trans_params.dat
        trans_capital_cost_per_mw_km, trans_lifetime_yrs,
        trans_fixed_om_fraction, distribution_loss_rate


    """

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'transmission_lines.tab'),
        select=('TRANSMISSION_LINE', 'trans_lz1', 'trans_lz2',
                'trans_length_km', 'trans_efficiency', 'existing_trans_cap'),
        index=mod.TRANSMISSION_LINES,
        param=(mod.trans_lz1, mod.trans_lz2, mod.trans_length_km,
               mod.trans_efficiency, mod.existing_trans_cap))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'trans_optional_params.tab'),
        optional=True,
        select=('TRANSMISSION_LINE', 'trans_dbid', 'trans_derating_factor',
                'trans_terrain_multiplier', 'trans_new_build_allowed'),
        param=(mod.trans_dbid, mod.trans_derating_factor,
               mod.trans_terrain_multiplier, mod.trans_new_build_allowed))
    trans_params_path = os.path.join(inputs_dir, 'trans_params.dat')
    if os.path.isfile(trans_params_path):
        switch_data.load(filename=trans_params_path)


def post_solve(instance, outdir):
    mod = instance
    normalized_dat = [
        {
        	"TRANSMISSION_LINE": tx,
        	"PERIOD": p,
        	"trans_lz1": mod.trans_lz1[tx],
        	"trans_lz2": mod.trans_lz2[tx],
        	"trans_dbid": mod.trans_dbid[tx],
        	"trans_length_km": mod.trans_length_km[tx],
        	"trans_efficiency": mod.trans_efficiency[tx],
        	"trans_derating_factor": mod.trans_derating_factor[tx],
        	"TxCapacityNameplate": value(mod.TxCapacityNameplate[tx,p]),
        	"TxCapacityNameplateAvailable": value(mod.TxCapacityNameplateAvailable[tx,p]),
        	"TotalAnnualCost": value(mod.TxCapacityNameplate[tx,p] * mod.trans_cost_annual[tx])
        } for tx, p in mod.TRANSMISSION_LINES * mod.PERIODS
    ]
    tx_build_df = pd.DataFrame(normalized_dat)
    tx_build_df.set_index(["TRANSMISSION_LINE", "PERIOD"], inplace=True)
    tx_build_df.to_csv(os.path.join(outdir, "transmission.csv"))
