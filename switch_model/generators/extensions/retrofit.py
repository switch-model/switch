import os
from pyomo.environ import *
from switch_model.utilities import unique_list
from switch_model.financials import capital_recovery_factor as crf

"""
This module makes it possible to define retrofits for existing generators. These
are done by defining a new generation project that can replace a previously
built one (i.e., it performs like the original generator plus the retrofit) and
adding columns to `gen_retrofits.csv` showing all allowed combinations of base
projects that can be replaced by retrofit projects. In each row,
`base_gen_project` shows the name of the original (base) project and
`retrofit_gen_project` shows the name of a retrofit project that can replace it.

Retrofit projects will only be built if the base project has also been built in
the same or an earlier period. When a base project is retrofitted, the base
project is suspended (via SuspendGen) and the retrofit version is built and
operated instead. In addition, retrofit projects are automatically suspended at
the end of life of the base project. (To enable these behaviors,
gen_can_retire_early or gen_can_suspend must be set to True or 1 in gen_info.csv
for both the base project and the retrofit version.)

Because of this framing, retrofitted projects will have capital expenditure
equal to the capital recovery for the base project plus capital recovery for the
retrofit project. So gen_overnight_cost for the retrofit project should be set
equal to the cost of the retrofit work, not the combined project. However, fixed
and variable O&M will no longer be collected for the base project, so O&M cost
inputs for the retrofit project should be the ones that apply for the total
retrofitted project.

Capital recovery for the retrofitted project will be amortized over the
remaining life of the base project that it replaces, which may cause faster
capital recovery than would otherwise be expected for these assets.
"""

"""
TODO: report total unavailable capacity (due to base retirements) somewhere,
possibly in gen_cap.csv, possibly just as a reduction in SuspendGen

TODO: more generally, it would be nice to be able to affect GenCapacity from
other modules, e.g. declare retrofitted and unavailable capacity in this module
and have them reduce GenCapacity (probably per vintage first, then in
aggregate), with a rule that GenCaoacity per vintage must never be negative.
That would simplify the code (no need to check for built capacity to suspend)
and allow decoupling (e.g. separate suspend module from build) and also clarify
special states in the output files (can't currently distinguish between
unavailable retrofit capacity and early retired, and have to jump through hoops
to dustinguish retrofitted base gens from early retired ones.) This may require
making a list of capacity adjustments and then creating GenCapacity in commit or
dispatch module (or just automatically apply UnavailableGen and SuspendGen and
if found).
"""


def define_components(m):
    # all allowed pairs of base project and retrofit (not used much)
    m.BASE_RETROFIT_PAIRS = Set(
        dimen=2, within=m.GENERATION_PROJECTS * m.GENERATION_PROJECTS
    )

    # set of all generation projects that can have retrofits
    def BASE_GENS_init(m):
        # build dict of all allowed retrofits for each gen, to initialize the
        # set of retrofitable gens and also the indexed set of retrofits for
        # each of them
        d = m.GEN_RETROFITS_dict = dict()
        for base, retro in m.BASE_RETROFIT_PAIRS:
            d.setdefault(base, []).append(retro)
        return list(d.keys())

    m.BASE_GENS = Set(initialize=BASE_GENS_init, within=m.GENERATION_PROJECTS)

    m.RETRO_GENS = Set(
        within=m.GENERATION_PROJECTS,
        initialize=lambda m: unique_list(
            ret_gen for (base_gen, ret_gen) in m.BASE_RETROFIT_PAIRS
        ),
    )

    # indexed set of retrofits that are possible for each retrofitable project
    m.RETROS_FOR_BASE = Set(
        m.BASE_GENS, initialize=lambda m, g: m.GEN_RETROFITS_dict.pop(g)
    )

    # set of all gens and bld_yrs that can later have retrofits
    m.BASE_BLD_YRS = Set(
        dimen=2,
        within=m.GEN_BLD_YRS,
        initialize=lambda m: [
            (g, p) for g in m.BASE_GENS for p in m.BLD_YRS_FOR_GEN[g]
        ],
    )

    # set of all retrofit gens and possible bld_yrs
    m.RETRO_BLD_YRS = Set(
        dimen=2,
        within=m.GEN_BLD_YRS,
        initialize=lambda m: [
            (g, p) for g in m.RETRO_GENS for p in m.BLD_YRS_FOR_GEN[g]
        ],
    )

    # Set of all vintages that can be retrofitted and allowed (retrofit, period)
    # combinations to do the retrofit
    m.BASE_BLD_RETRO_BLD = Set(
        initialize=lambda m: [
            (base_gen, bld_yr, ret_gen, ret_yr)
            # base gen and vintage
            for base_gen, bld_yr in m.BASE_BLD_YRS
            # gens that can retrofit it
            for ret_gen in m.RETROS_FOR_BASE[base_gen]
            # years when that vintage operates so it could be retrofitted
            for ret_yr in m.PERIODS_FOR_GEN_BLD_YR[base_gen, bld_yr]
            # ignore times when the retrofit gen is unavailable
            if (ret_gen, ret_yr) in m.GEN_BLD_YRS
        ]
    )

    # list of all possible (retrofit, build year) combinations
    # that could be applied to the specified (base gen, build year)
    # combination
    def RETRO_BLD_FOR_BASE_BLD_init(m, base_gen, bld_yr):
        try:
            d = m.RETRO_BLD_FOR_BASE_BLD_dict
        except AttributeError:
            d = m.RETRO_BLD_FOR_BASE_BLD_dict = {(g, p): [] for g, p in m.BASE_BLD_YRS}
            for _base_gen, _bld_yr, ret_gen, ret_yr in m.BASE_BLD_RETRO_BLD:
                d[_base_gen, _bld_yr].append((ret_gen, ret_yr))
        return d.pop((base_gen, bld_yr))

    m.RETRO_BLD_FOR_BASE_BLD = Set(
        m.BASE_BLD_YRS,
        dimen=2,
        within=m.GEN_BLD_YRS,
        initialize=RETRO_BLD_FOR_BASE_BLD_init,
    )

    # set of years when a base generator built in a certain year
    # can have operation suspended
    m.BASE_BLD_SUSPEND_YRS = Set(
        dimen=3,
        within=m.BASE_BLD_YRS * m.PERIODS,
        initialize=lambda m: [
            (base_gen, bld_yr, sus_yr)
            for base_gen, bld_yr in m.BASE_BLD_YRS
            for sus_yr in m.PERIODS_FOR_GEN_BLD_YR[base_gen, bld_yr]
        ],
    )

    # retrofits that will be performed
    m.BuildRetrofitGen = Var(m.BASE_BLD_RETRO_BLD, within=NonNegativeReals)

    # make sure total retrofit builds match the BuildGen value each year
    # (don't allow building retrofit gens as non-retrofits)
    def Allocate_Retrofit_Builds_rule(m, ret_gen, ret_yr):
        try:
            d = m.Allocate_Retrofit_Builds_dict
        except AttributeError:
            d = m.Allocate_Retrofit_Builds_dict = {
                (g, y): [] for g, y in m.RETRO_BLD_YRS
            }
            # find all the BuildRetrofitGen vars that correspond to each
            # (retrofit gen, retrofit build year) combination

            # scan all possible GenBuildRetrofit choices
            for _base_gen, _bld_yr, _ret_gen, _ret_yr in m.BASE_BLD_RETRO_BLD:
                # assign to the appropriate ret_gen, ret_yr list
                d[_ret_gen, _ret_yr].append(
                    m.BuildRetrofitGen[_base_gen, _bld_yr, _ret_gen, _ret_yr]
                )

        retrofit_builds = d.pop((ret_gen, ret_yr))
        return sum(retrofit_builds) == m.BuildGen[ret_gen, ret_yr]

    m.Allocate_Retrofit_Builds = Constraint(
        m.RETRO_BLD_YRS, rule=Allocate_Retrofit_Builds_rule
    )

    # require sum of all retrofits on those vintages to be less than the
    # quantity installed
    m.Only_Retrofit_Built_Capacity = Constraint(
        m.BASE_BLD_YRS,
        rule=lambda m, base_gen, bld_yr: sum(
            m.BuildRetrofitGen[base_gen, bld_yr, ret_gen, ret_yr]
            for ret_gen, ret_yr in m.RETRO_BLD_FOR_BASE_BLD[base_gen, bld_yr]
        )
        <= m.BuildGen[base_gen, bld_yr],
    )

    # force suspension of retrofitted vintages of base plant over remaining
    # life of plant (total suspensions >= sum of all retrofits on those vintages in
    # prior years)
    m.Always_Suspend_Retrofitted_Base_Gens = Constraint(
        m.BASE_BLD_SUSPEND_YRS,
        rule=lambda m, base_gen, bld_yr, sus_yr: m.SuspendGen[base_gen, bld_yr, sus_yr]
        >= sum(
            m.BuildRetrofitGen[base_gen, bld_yr, ret_gen, ret_yr]
            for ret_gen, ret_yr in m.RETRO_BLD_FOR_BASE_BLD[base_gen, bld_yr]
            if m.PERIODS.ord(ret_yr) <= m.PERIODS.ord(sus_yr)
        ),
    )

    # force suspension of retrofits after their base plant max age
    # (suspensions of retro gens in each year must at least equal
    # retro gen capacity that is over its base gen's life in that
    # period)

    # change to EXCESS_BASE_BLD_FOR_RETRO_BLD_PERIOD
    # and convert code below to build the relevant dictionary
    # or maybe build the set below once, then use it to construct
    # the EXCESS_BASE_BLD_FOR_RETRO_BLD_PERIOD set and also the
    # RETRO_BLD_SUSPEND_YRS set (like GEN_BLD_SUSPEND_YRS but only
    # for retro gens)
    # Or can we just build RETRO_BLD_SUSPEND_YRS and for each entry,
    # directly identify the base bld yrs that will be aged out by now?

    # identify (retro gen, retro yr, operating yr) combinations that are at
    # least partly beyond the retirement date for the corresponding base gen
    # and identify (base gen, build yr) combinations that are out of service
    # at this point
    def EXCESS_RETRO_BLD_PERIODS_init(m):
        # build a dictionary identifying all the past-life retrofits and showing
        # all the retired base gen vintages for each one
        try:
            d = m.EXCESS_BASE_BLD_FOR_RETRO_BLD_PERIOD_dict
        except AttributeError:
            d = m.EXCESS_BASE_BLD_FOR_RETRO_BLD_PERIOD_dict = dict()
            # all possible retrofits
            for base_gen, bld_yr, ret_gen, ret_yr in m.BASE_BLD_RETRO_BLD:
                # all possible operating periods for the retrofit gen
                for op_yr in m.PERIODS_FOR_GEN_BLD_YR[ret_gen, ret_yr]:
                    # periods when the base gen vintage cannot run
                    if op_yr not in m.PERIODS_FOR_GEN_BLD_YR[base_gen, bld_yr]:
                        # save the (base gens, base build year) pairs that are
                        # now past retirement; these retrofits will later be
                        # forced to be suspended
                        d.setdefault((ret_gen, ret_yr, op_yr), []).append(
                            (base_gen, bld_yr)
                        )
        return list(d.keys())

    # Note: these are not _all_ out of service, just partly
    m.EXCESS_RETRO_BLD_PERIODS = Set(
        dimen=3,
        within=m.GEN_BLD_YRS * m.PERIODS,
        initialize=EXCESS_RETRO_BLD_PERIODS_init,
    )

    m.EXCESS_BASE_BLD_FOR_RETRO_BLD_PERIOD = Set(
        m.EXCESS_RETRO_BLD_PERIODS,
        dimen=2,
        within=m.GEN_BLD_YRS,
        initialize=lambda m, ret_gen, ret_yr, op_yr: m.EXCESS_BASE_BLD_FOR_RETRO_BLD_PERIOD_dict.pop(
            (ret_gen, ret_yr, op_yr)
        ),
    )

    m.Force_Suspension_of_Retrofits_After_Base_Retires = Constraint(
        # needs to be an index of RETRO_PERIODS, and force SuspendGen(retro_gen, p)
        # to at least equal all the retro capacity of that type that is now in
        # excess periods.
        m.EXCESS_RETRO_BLD_PERIODS,
        rule=lambda m, ret_gen, ret_yr, op_yr: m.SuspendGen[ret_gen, ret_yr, op_yr]
        >= sum(
            m.BuildRetrofitGen[base_gen, bld_yr, ret_gen, ret_yr]
            for (base_gen, bld_yr) in m.EXCESS_BASE_BLD_FOR_RETRO_BLD_PERIOD[
                ret_gen, ret_yr, op_yr
            ]
        ),
    )

    # Amortize retrofits over remaining life of base plant or retrofit, whichever
    # is shorter; this subtracts the normal amortization done for the retrofit
    # in generators.core.build and then adds the same calculation with
    # a shorter life

    def retro_capital_cost_annual_init(m, base_gen, bld_yr, ret_gen, ret_yr):
        # Calculate annual costs over life of retrofit, possibly shorter than
        # normal life due to automatic retirement of base gen.

        # retirement logic from gen_build_can_operate_in_period in gen.build
        base_start = m.period_start[bld_yr] if bld_yr in m.PERIODS else bld_yr
        base_stop = base_start + m.gen_max_age[base_gen]
        retro_start = m.period_start[ret_yr]
        retro_stop_long = retro_start + m.gen_max_age[ret_gen]
        retro_stop = min(base_stop, retro_stop_long)

        # same calculation as m.gen_capital_cost_annual, but with adjusted life
        annual_cost = (
            m.gen_overnight_cost[ret_gen, ret_yr] + m.gen_connect_cost_per_mw[ret_gen]
        ) * crf(m.interest_rate, retro_stop - retro_start)
        return annual_cost

    m.retro_capital_cost_annual = Param(
        m.BASE_BLD_RETRO_BLD,
        within=NonNegativeReals,
        initialize=retro_capital_cost_annual_init,
    )

    # eventually just need a total adjustment per period; could build to that or
    # just get the total directly
    # building to it via retro gen and period (similar to GenCapitalCosts) or
    # possibly retro_gen, period and base vintage) might be helpful for diagnosis.

    # Calculate the capital cost for each retrofit gen in each period (0 if
    # unavailable). This considers all the BuildRetrofitGen choices and applies
    # the accelerated amortization (retro_capital_cost_annual) during the
    # periods when neither the retrofit nor its base gen are past max_age_years.
    def RetrofitCapitalCost_init(m, ret_gen, op_per):
        try:
            d = m.RetrofitCapitalCost_dict
        except AttributeError:
            d = m.RetrofitCapitalCost_dict = dict()
            # Scan all the BuildRetrofitGen decisions and apply the relevant
            # cost in all periods when that retrofit and its base gen could
            # operate.

            # all possible GenBuildRetrofit choices
            for _base_gen, _bld_yr, _ret_gen, _ret_yr in m.BASE_BLD_RETRO_BLD:
                # all possible operating years for this choice
                for _op_per in m.PERIODS_FOR_GEN_BLD_YR[_ret_gen, _ret_yr]:
                    # exclude periods when the base gen is out of operation
                    if (_base_gen, _op_per) in m.GEN_PERIODS:
                        # add the annual cost for this period
                        d.setdefault((_ret_gen, _op_per), []).append(
                            (_base_gen, _bld_yr, _ret_gen, _ret_yr)
                        )

        keys = d.pop((ret_gen, op_per), [])
        # calculating the sum from the keys is faster than saving
        # the individual cost terms and summing them here
        capital_cost = sum(
            m.BuildRetrofitGen[k] * m.retro_capital_cost_annual[k]
            for k in keys  # k is a _base_gen, _bld_yr, _ret_gen, _ret_yr tuple
        )
        return capital_cost

    m.RetrofitCapitalCost = Expression(
        m.RETRO_GENS, m.PERIODS, rule=RetrofitCapitalCost_init
    )

    # add the retrofit gen capital cost with accelerated amortization
    # and cancel the capital cost with normal amortization
    m.GenRetrofitCapitalCostAdjustment = Expression(
        m.PERIODS,
        rule=lambda m, p: sum(
            m.RetrofitCapitalCost[g, p] - m.GenCapitalCosts[g, p] for g in m.RETRO_GENS
        ),
    )
    m.Cost_Components_Per_Period.append("GenRetrofitCapitalCostAdjustment")


def load_inputs(m, switch_data, inputs_dir):
    """
    gen_retrofits.csv lists all projects that can be done as a retrofit
    on each standard project.

    gen_retrofits.csv
    base_gen_project, retrofit_gen_project
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "gen_retrofits.csv"),
        set=m.BASE_RETROFIT_PAIRS,
    )
