"""

Defines model components to describe transmission build-outs for the
SWITCH-Pyomo model.

SYNOPSIS
>>> from pyomo.environ import *
>>> import utilities
>>> switch_modules = ('timescales', 'financials', 'load_zones', 'trans_build')
>>> utilities.load_switch_modules(switch_modules)
>>> switch_model = utilities.define_AbstractModel(switch_modules)
>>> inputs_dir = 'test_dat'
>>> switch_data = utilities.load_data(switch_model, inputs_dir, switch_modules)
>>> switch_instance = switch_model.create(switch_data)

Note, this can be tested with `python -m doctest -v trans_build.py`

Switch-pyomo is licensed under Apache License 2.0 More info at switch-model.org
"""

import os
from pyomo.environ import *
import utilities
from timescales import hours_per_year
from financials import capital_recovery_factor as crf


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe
    transmission and distribution portions of an electric grid. This
    includes parameters, build decisions and constraints.
    Unless otherwise stated, all power capacity is specified in units of
    MW and all sets and parameters are mandatory.

    TRANSMISSION_LINES is the complete set of transmission pathways
    connecting load zones. Each member of this set is a one dimensional
    identifier such as "A-B". This set has no regard for directionality
    of transmisison lines and will generate an error if you specify two
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

    TRANS_BUILD_YEARS is the set of transmission lines and years in
    which they have been or could be built. This set includes past and
    potential future builds. All future builds must come online in the
    first year of an investment period. This set is composed of two
    elements with members: (tx, build_year). For existing transmission
    where the build years are not known, build_year is set to 'Legacy'.

    EXISTING_TRANS_BLD_YRS is a subset of TRANS_BUILD_YEARS that lists
    builds that happened before the first investment period. For most
    datasets the build year is unknown, so is it always set to 'Legacy'.

    existing_trans_cap[tx in TRANSMISSION_LINES] is a parameter that
    describes how many MW of capacity has been installed before the
    start of the study.

    NEW_TRANS_BLD_YRS is a subset of TRANS_BUILD_YEARS that describes
    potential builds.

    BuildTrans[(tx, bld_yr) in TRANS_BUILD_YEARS] is a decision variable
    that describes the transfer capacity in MW installed on a cooridor
    in a given build year. For existing builds, this variable is locked
    to the existing capacity.

    TransCapacity[(tx, bld_yr) in TRANS_BUILD_YEARS] is an expression
    that returns the total nameplate transfer capacity of a transmission
    line in a given period. This is the sum of existing and newly-build
    capacity.

    trans_derating_factor[tx in TRANSMISSION_LINES] is an overall
    derating factor for each transmission line that can reflect forced
    outage rates, stability or contingency limitations. This parameter
    is optional and defaults to 0.

    TransCapacityAvailable[(tx, bld_yr) in TRANS_BUILD_YEARS] is an
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

    trans_fixed_o_m_fraction is describes the fixed Operations and
    Maintenance costs as a fraction of capital costs. This optional
    parameter defaults to 0.03 based on 2009 WREZ transmission model
    transmission data costs for existing transmission maintenance.

    trans_cost_hourly[tx TRANSMISSION_LINES] is the cost of building
    transmission lines in units of $BASE_YEAR / MW- transfer-capacity /
    hour. This derived parameter is based on the total annualized
    capital and fixed O&M costs, then divides that by hours per year to
    determine the portion of costs incurred hourly.

    TRANS_DIRECTIONAL is a derived set of directional paths that
    electricity can flow along transmission lines. Each element of this
    set is a two-dimensional entry that describes the origin and
    destination of the flow: (load_zone_from, load_zone_to). Every
    transmission line will generate two entries in this set. Members of
    this set are abbreviated as trans_d where possible, but may be
    abbreviated as tx in situations where brevity is important and it is
    unlikely to be confused with the overall transmission line.

    trans_d_line[trans_d] is the transmission line associated with this
    directional path.

    LOCAL_TD_BUILD_YEARS is the set of load zones with local
    transmission and distribution and years in which construction has or
    could occur. This set includes past and potential future builds. All
    future builds must come online in the first year of an investment
    period. This set is composed of two elements with members:
    (load_zone, build_year). For existing capacity where the build year
    is unknown or spread out over time, build_year is set to 'Legacy'.

    EXISTING_LOCAL_TD_BLD_YRS is a subset of LOCAL_TD_BUILD_YEARS that
    lists builds that happened before the first investment period. For
    most datasets the build year is unknown, so is it always set to
    'Legacy'.

    existing_local_td[lz in LOAD_ZONES] is the amount of local
    transmission and distribution capacity in MW that has already been
    built.

    BuildLocalTD[(lz, bld_yr) in LOCAL_TD_BUILD_YEARS] is a decision
    variable describing how much local transmission and distribution to
    build in a load zone. For existing builds, this variable is locked
    to existing capacity. Without demand response, the optimal value of
    this variable is trivially computed based on the load zone's peak
    expected load. With demand response, this decision becomes less
    obvious in high solar conditions where it may be desirable to shift
    some demand from evening into afternoon to coincide with the solar
    peak.

    LocalTDCapacity[lz, period] is an expression that describes how much
    local transmission and distribution has been built to date in each
    load zone.

    distribution_losses is the proportion of energy that is lost in the
    local transmission & distribution system before delivery. This value
    is relative to delivered energy, so the total energy needed is load
    * (1 + distribution_losses). This optional value defaults to 0.053
    based on ReEDS Solar Vision documentation:
    http://www1.eere.energy.gov/solar/pdfs/svs_appendix_a_model_descriptions_data.pdf

    Meet_Local_TD[lz, period] is a constraint that enforces minimal
    local T&D requirements. Demand response may specify a more complex
    constraint.

        LocalTDCapacity >= max_local_demand

    local_td_lifetime_yrs is a parameter describing the physical and
    financial lifetime of local transmission & distribution. This
    parameter is optional and defaults to 20 years.

    local_td_cost_per_mw[lz in LOAD_ZONES] describes the total annual
    costs for each MW of local transmission & distributino. This value
    should include the annualized capital costs as well as fixed
    operations & maintenance costs. These costs will be applied to
    existing and new infrastructure. We assume that existing capacity
    will be replaced at the end of its life, so these costs will
    continue indefinitely.

    --- Delayed implementation ---

    # TRANS_BUILD_OPERATIONAL_PERIODS[(tx, bld_yr) in TRANS_BUILD_YEARS]
    # is an indexed set that describes which periods a given transmission
    # build will be operational. Currently, transmission lines are kept
    # online indefinitely, with parts being replaced as they wear out.

    distributed PV don't incur distribution_losses..

    is_dc_line ... Do I even need to implement this?

    local_td_sunk_annual_payment[lz in LOAD_ZONES] .. this was in the
    old model. It would be cleaner if I could copy the pattern for
    project_build where existing projects have the same data structure
    as new projects which includes both an installation date and
    retirement date. For that to work, I would need to knew (or
    estimate) the installation date of existing infrastructure so we
    could know when it needed to be replaced. The old implementation
    assumed a different annual cost of new and existing local T&D. The
    existing infrastructure was expected to remain online indefinitely
    at those costs. The new infrastructure was expected to be retired
    after 20 years, after which new infrastructure would be installed
    via the InstallLocalTD decision variable. The annual costs for
    existing infrastructure were 22-99 percent higher that for new
    infrastructure in the standard WECC datasets, but I don't know the
    reason for the discrepancy.



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

    SWITCH-Pyomo assumes all transmission and distribution (long-
    distance or local) the same. Any capacity that is built will be kept
    online indefinitely. At the end of its financial lifetime, existing
    capacity will be retired and rebuilt, so the annual cost of a line
    upgrade will remain constant in every future year.

    """

    # This will add a min_data_check() method to the model
    utilities.add_min_data_check(mod)

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
    mod.EXISTING_TRANS_BLD_YRS = Set(
        dimen=2,
        initialize=lambda m: set(
            (tx, 'Legacy') for tx in m.TRANSMISSION_LINES))
    mod.existing_trans_cap = Param(
        mod.TRANSMISSION_LINES,
        within=PositiveReals)
    mod.min_data_check(
        'trans_length_km', 'trans_efficiency', 'EXISTING_TRANS_BLD_YRS',
        'existing_trans_cap')
    mod.trans_new_build_allowed = Param(
        mod.TRANSMISSION_LINES, within=Boolean, default=True)
    mod.NEW_TRANS_BLD_YRS = Set(
        dimen=2,
        initialize=lambda m: m.TRANSMISSION_LINES * m.INVEST_PERIODS,
        filter=lambda m, tx, p: m.trans_new_build_allowed[tx])
    mod.TRANS_BUILD_YEARS = Set(
        dimen=2,
        initialize=lambda m: m.EXISTING_TRANS_BLD_YRS | m.NEW_TRANS_BLD_YRS)

    def bounds_BuildTrans(model, tx, bld_yr):
        if((tx, bld_yr) in model.EXISTING_TRANS_BLD_YRS):
            return (model.existing_trans_cap[tx],
                    model.existing_trans_cap[tx])
        else:
            return (0, None)
    mod.BuildTrans = Var(
        mod.TRANS_BUILD_YEARS,
        within=NonNegativeReals,
        bounds=bounds_BuildTrans)
    mod.TransCapacity = Expression(
        mod.TRANSMISSION_LINES, mod.INVEST_PERIODS,
        initialize=lambda m, tx, period: sum(
            m.BuildTrans[tx, bld_yr]
            for (tx2, bld_yr) in m.TRANS_BUILD_YEARS
            if tx2 == tx and (bld_yr == 'Legacy' or bld_yr <= period)))
    mod.trans_derating_factor = Param(
        mod.TRANSMISSION_LINES,
        within=NonNegativeReals,
        default=0,
        validate=lambda m, val, tx: val <= 1)
    mod.TransCapacityAvailable = Expression(
        mod.TRANSMISSION_LINES, mod.INVEST_PERIODS,
        initialize=lambda m, tx, period: (
            m.TransCapacity[tx, period] * m.trans_derating_factor[tx]))
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
    mod.trans_fixed_o_m_fraction = Param(
        within=PositiveReals,
        default=0.03)
    # Total fixed costs per hour for building new transmission lines...
    # Multiply capital costs by capital recover factor to get annual
    # payments. Add annual fixed O&M that are expressed as a fraction of
    # overnight costs. Divide by the hours in a year to get the hourly
    # fixed costs.
    mod.trans_cost_hourly = Param(
        mod.TRANSMISSION_LINES,
        within=PositiveReals,
        initialize=lambda m, tx: (
            m.trans_capital_cost_per_mw_km * m.trans_terrain_multiplier[tx] *
            (crf(m.interest_rate, m.trans_lifetime_yrs) +
                m.trans_fixed_o_m_fraction) / hours_per_year))

    def init_TRANS_DIRECTIONAL(model):
        tx_dir = set()
        for tx in model.TRANSMISSION_LINES:
            tx_dir.add((model.trans_lz1[tx], model.trans_lz2[tx]))
            tx_dir.add((model.trans_lz2[tx], model.trans_lz1[tx]))
        return tx_dir
    mod.TRANS_DIRECTIONAL = Set(
        dimen=2,
        initialize=init_TRANS_DIRECTIONAL)

    def init_trans_d_line(m, lz_from, lz_to):
        for tx in m.TRANSMISSION_LINES:
            if((m.trans_lz1[tx] == lz_from and m.trans_lz2[tx] == lz_to) or
               (m.trans_lz2[tx] == lz_from and m.trans_lz1[tx] == lz_to)):
                return tx
    mod.trans_d_line = Param(
        mod.TRANS_DIRECTIONAL,
        within=mod.TRANSMISSION_LINES,
        initialize=init_trans_d_line)

    ######################
    # Local Transmission & Distribution stuff
    mod.EXISTING_LOCAL_TD_BLD_YRS = Set(
        dimen=2,
        initialize=lambda m: set((lz, 'Legacy') for lz in m.LOAD_ZONES))
    mod.existing_local_td = Param(mod.LOAD_ZONES, within=NonNegativeReals)
    mod.min_data_check('existing_local_td')
    mod.LOCAL_TD_BUILD_YEARS = Set(
        dimen=2,
        initialize=lambda m: set(
            (m.LOAD_ZONES * m.INVEST_PERIODS) | m.EXISTING_LOCAL_TD_BLD_YRS))

    def bounds_BuildLocalTD(model, lz, bld_yr):
        if((lz, bld_yr) in model.EXISTING_LOCAL_TD_BLD_YRS):
            return (model.existing_local_td[lz],
                    model.existing_local_td[lz])
        else:
            return (0, None)
    mod.BuildLocalTD = Var(
        mod.LOCAL_TD_BUILD_YEARS,
        within=NonNegativeReals,
        bounds=bounds_BuildLocalTD)
    mod.LocalTDCapacity = Expression(
        mod.LOAD_ZONES, mod.INVEST_PERIODS,
        initialize=lambda m, lz, period: sum(
            m.BuildLocalTD[lz, bld_yr]
            for (lz2, bld_yr) in m.LOCAL_TD_BUILD_YEARS
            if lz2 == lz2 and (bld_yr == 'Legacy' or bld_yr <= period)))
    mod.distribution_losses = Param(default=0.053)
    mod.Meet_Local_TD = Constraint(
        mod.LOAD_ZONES, mod.INVEST_PERIODS,
        rule=lambda m, lz, period: (
            m.LocalTDCapacity[lz, period] >= m.lz_peak_demand_mw[lz, period]))
    mod.local_td_lifetime_yrs = Param(default=20)
    mod.local_td_cost_per_mw = Param(
        mod.LOAD_ZONES,
        within=PositiveReals)
    mod.min_data_check('local_td_cost_per_mw')


def load_data(mod, switch_data, inputs_dir):
    """

    Import data related to transmission builds. The following files are
    expected in the input directory:

    transmission_lines.tab
        TRANSMISSION_LINE, trans_lz1, trans_lz2, trans_length_km,
        trans_efficiency, existing_trans_cap

    local_td.tab
        load_zone, existing_local_td, local_td_cost_per_mw

    The next files are optional. If they are not included or if any rows
    are missing, those parameters will be set to default values as
    described in documentation. You may specify 'default' in any field
    of trans_optional_params.tab if you only wish to override certain
    default values for a particular row.

    trans_optional_params.tab
        TRANSMISSION_LINE, trans_dbid, trans_derating_factor,
        trans_terrain_multiplier, trans_new_build_allowed

    Note that the next file is formatted as .dat, not as .tab.

    trans_params.dat
        trans_capital_cost_per_mw_km, trans_lifetime_yrs,
        trans_fixed_o_m_fraction, distribution_losses, local_td_lifetime_yrs,
        local_td_cost_per_mw


    """

    switch_data.load(
        filename=os.path.join(inputs_dir, 'transmission_lines.tab'),
        select=('TRANSMISSION_LINE', 'trans_lz1', 'trans_lz2',
                'trans_length_km', 'trans_efficiency', 'existing_trans_cap'),
        index=mod.TRANSMISSION_LINES,
        param=(mod.trans_lz1, mod.trans_lz2, mod.trans_length_km,
               mod.trans_efficiency, mod.existing_trans_cap))
    switch_data.load(
        filename=os.path.join(inputs_dir, 'local_td_existing.tab'),
        select=('load_zone', 'existing_local_td', 'local_td_cost_per_mw'),
        param=(mod.existing_local_td, mod.local_td_cost_per_mw))
    trans_optional_params_path = os.path.join(
        inputs_dir, 'trans_optional_params.tab')
    if os.path.isfile(trans_optional_params_path):
        switch_data.load(
            filename=trans_optional_params_path,
            select=('TRANSMISSION_LINE', 'trans_dbid', 'trans_derating_factor',
                    'trans_terrain_multiplier', 'trans_new_build_allowed'),
            param=(mod.trans_dbid, mod.trans_derating_factor,
                   mod.trans_terrain_multiplier, mod.trans_new_build_allowed))
    # Optional parameters with default values can have values of 'default' in
    # the input file. Find and delete those entries to prevent type errors.
    opt_param_list = ['trans_dbid', 'trans_derating_factor',
                      'trans_terrain_multiplier', 'trans_new_build_allowed']
    for tx in switch_data.data(name='TRANSMISSION_LINES'):
        for opt_param in opt_param_list:
            if(opt_param in switch_data.data() and
               switch_data.data(name=opt_param)[tx] == 'default'):
                del switch_data.data(name=opt_param)[tx]
    trans_params_path = os.path.join(inputs_dir, 'trans_params.dat')
    if os.path.isfile(trans_params_path):
        switch_data.load(filename=trans_params_path)
