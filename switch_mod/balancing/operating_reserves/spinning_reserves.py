# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
A simple and flexible model of spinning reserves. Spinning reserve
requirements can be customized through use of configuration parameters and can
include n-1 contigencies (either from generation units or entire generation
plants), as well as variability of load and variable renewable resources. This
lumps together regulating reserves, load following reserves, and contigency
reserves without distinguishing their timescales or required response
duration. Operating reserves at timescales with slower responses for load
following or longer-term recovery from contigencies are not included here.

Most regions and countries use distinct terminology for reserves products and
distinct procedures for determining reserve requirements. This module provides
a simple approach to spinning reserve requirements. Detailed regional studies
will need to write their own reserve modules to reflect regional reserve
definitions and policies. 

Notes: 

This formulation only considers ramping capacity, not duration. The lack of
duration requirements could cause problems if a significant amount of capacity
is energy limited such as demand response, storage, or hydro.

One standard (nonlinear) methodology for calculating reserve requirements
looks something like: k * sqrt(sigma_load^2 + sigma_renewable^2), where k is a
constant reflecting capacity requirements (typically in the range of 3-5), and
sigma's denote standard deviation in units of MW. Depending on the study,
sigma may be calculated on timescales of seconds to minutes. Several studies
estimate the sigmas with linear approximations. Some studies set
sigma_renewable as a function of renewable output, especially for wind where
power output shows the highest variability in the 40-60% output range because
that is the steepest section of its power production curve. This formulation
is not used here because the signma_renewable term would need to be
approximated using renewable power output, making this equation non-linear
with respect to dispatch decision variables.

Other studies have used linear equations for estimating reserve requirements:

The Western Wind and Solar Integration study suggested a heuristic of 3% *
load + 5% * renewable_output for spinning reserve capacity requirements, and
the same amount for quick start capacity requirements.

Halamay 2011 derives spinning reserve requirements of +2.1% / -2.8% of load
and ~ +2% / -3% for renewables to balance natural variability, and derives
non-spinning reserve requirements and +3.5% / -4.0% of load and ~ +/- 4% for
renewables to balance hour-ahead forecast errors.

Note: Most research appears to be headed towards dynamic and probabilistic
techniques, rather than the static approximations used here. 

References on operating reserves follow.

Ela, Erik, et al. "Evolution of operating reserve determination in wind power
integration studies." Power and Energy Society General Meeting, 2010 IEEE.
http://www.nrel.gov/docs/fy11osti/49100.pdf

Milligan, Michael, et al. "Operating reserves and wind power integration: An
international comparison." proc. 9th International Workshop on large-scale
integration of wind power into power systems. 2010.
http://www.nrel.gov/docs/fy11osti/49019.pdf

Halamay, Douglas A., et al. "Reserve requirement impacts of large-scale
integration of wind, solar, and ocean wave power generation." IEEE
Transactions on Sustainable Energy 2.3 (2011): 321-328.
http://nnmrec.oregonstate.edu/sites/nnmrec.oregonstate.edu/files/PES_GM_2010_HalamayVariability_y09m11d30h13m26_DAH.pdf

Ibanez, Eduardo, Ibrahim Krad, and Erik Ela. "A systematic comparison of
operating reserve methodologies." PES General Meeting| Conference &
Exposition, 2014 IEEE. http://www.nrel.gov/docs/fy14osti/61016.pdf

"""
import os
from pyomo.environ import *

dependencies = (
    'switch_mod.timescales',
    'switch_mod.balancing.load_zones',
    'switch_mod.balancing.operating_reserves.areas',
    'switch_mod.financials',
    'switch_mod.energy_sources.properties',
    'switch_mod.generators.core.build',
    'switch_mod.generators.core.dispatch',
    'switch_mod.generators.core.commit.operate',    
)


def define_arguments(argparser):
    group = argparser.add_argument_group(__name__)
    group.add_argument('--unit-contigency', default=False, 
        dest='unit_contigency', action='store_true',
        help=("This will enable an n-1 contingency based on a single unit of "
              "a generation project falling offline. Note: This create a new "
              "binary variable for each project and timepoint that has a "
              "proj_unit_size specified.")
    )
    group.add_argument('--project-contigency', default=False, 
        dest='project_contigency', action='store_true',
        help=("This will enable an n-1 contingency based on the entire "
              "committed capacity of a generation project falling offline. "
              "Unlike unit contigencies, this is a purely linear expression.")
    )
    group.add_argument('--spinning-requirement-rule', default=None, 
        dest='spinning_requirement_rule', 
        choices = ["Hawaii", "3+5"],
        help=("Choose rules for spinning reserves requirements as a function "
              "of variable renewable power and load. Hawaii uses rules "
              "bootstrapped from the GE RPS study, and '3+5' requires 3% of "
              "load and 5% of variable renewable output, based on the heuristic "
              "described in the 2010 Western Wind and Solar Integration Study.")
    )
    
    


def define_dynamic_lists(m):
    """
    Spinning_Reserve_Up_Requirements and Spinning_Reserve_Down_Requirements
    are lists of model components that contribute to spinning reserve
    requirements in each balancing area and timepoint. 
    
    Spinning_Reserve_Up_Provisions and Spinning_Reserve_Down_Provisions are
    lists of model components that help satisfy spinning reserve requirements
    in each balancing area and timepoint. 
    
    Spinning_Reserve_Contigencies is a list of model components
    describing maximum contigency events. Elements of this list will be 
    summarized into a MaximumContigency variable that will be added to the
    Spinning_Reserve_Up_Requirements list.
    
    Each component in every list needs to use units of MW and be indexed by:
    (b, t) in BALANCING_AREA_TIMEPOINTS.
    """
    m.Spinning_Reserve_Up_Requirements = []
    m.Spinning_Reserve_Down_Requirements = []
    m.Spinning_Reserve_Up_Provisions = []
    m.Spinning_Reserve_Down_Provisions = []
    m.Spinning_Reserve_Contigencies = []


def gen_unit_contigency(m):
    """
    Add components for unit-level contigencies. This will add binary variables
    to the model for every GEN_TPS that has unit size specified.
    """
    # UNIT_CONTINGENCY_DISPATCH_POINTS duplicates
    # GEN_DISPATCH_POINTS_DISCRETE from generators.core.commit.discrete. I
    # justify the duplication because I don't think discrete unit commitment
    # should be a prerequisite for this functionality.
    m.UNIT_CONTINGENCY_DISPATCH_POINTS = Set(
        initialize=m.GEN_TPS, 
        filter=lambda m, g, tp: g in m.DISCRETELY_SIZED_GENS
    )
    m.GenIsCommitted = Var(m.UNIT_CONTINGENCY_DISPATCH_POINTS, within=Binary,
        doc="Stores the status of unit committment as a binary variable."
    )
    m.Enforce_GenIsCommitted = Constraint(
        m.UNIT_CONTINGENCY_DISPATCH_POINTS,
        rule=lambda m, g, tp: 
            m.CommitGen[g, tp] <= m.GenIsCommitted[g, tp] * (
                m._gen_max_cap_for_binary_constraints 
                if g not in m.CAPACITY_LIMITED_GENS
                else m.gen_capacity_limit_mw[g]
            )
    )
    m.GenUnitLargestContingency = Var(
        m.BALANCING_AREA_TIMEPOINTS,
        doc="Largest generating unit that could drop offline.")
    def Enforce_GenUnitLargestContingency_rule(m, g, t):
        b = m.zone_balancing_area[m.gen_load_zone[g]]
        return (m.GenUnitLargestContingency[b,t] >= 
                m.GenIsCommitted[g, t] * m.gen_unit_size[g])
    m.Enforce_GenUnitLargestContingency = Constraint(
        m.UNIT_CONTINGENCY_DISPATCH_POINTS,
        rule=Enforce_GenUnitLargestContingency_rule,
        doc=("Force GenUnitLargestContingency to be at least as big as the "
             "maximum unit contigency.")
    )
    m.Spinning_Reserve_Contigencies.append('GenUnitLargestContingency')


def gen_project_contigency(m):
    """
    Add components for project-level contigencies based on committed capacity
    """
    m.GenProjectLargestContingency = Var(
        m.BALANCING_AREA_TIMEPOINTS,
        doc="Largest generating project that could drop offline.")
    def Enforce_GenProjectLargestContingency_rule(m, g, t):
        b = m.zone_balancing_area[m.gen_load_zone[g]]
        return m.GenProjectLargestContingency[b, t] >= m.CommitGen[g, t]
    m.Enforce_GenProjectLargestContingency = Constraint(
        m.GEN_TPS,
        rule=Enforce_GenProjectLargestContingency_rule,
        doc=("Force GenProjectLargestContingency to be at least as big as the "
             "maximum generation project contigency.")
    )
    m.Spinning_Reserve_Contigencies.append('GenProjectLargestContingency')
    

def hawaii_spinning_reserve_requirements(m):
    # This stuff seems more appropriate for a hawaii submodule until it is
    # documented and referenced. I have a draft of this in a hawaii submodule, 
    # but haven't tested it yet. 
    # these parameters were found by regressing the reserve requirements from
    # the GE RPS Study against wind and solar conditions each hour (see
    # Dropbox/Research/Shared/Switch-Hawaii/ge_validation/source_data/
    # reserve_requirements_oahu_scenarios charts.xlsx and
    # Dropbox/Research/Shared/Switch-Hawaii/ge_validation/
    # fit_renewable_reserves.ipynb ) 
    # TODO: supply these parameters in input files
    m.var_gen_power_reserve = Param(
        m.VARIABLE_GENS, default=1.0,
        doc=("Spinning reserves required to back up variable renewable "
             "generators, as fraction of potential output.")
    )
    def var_gen_cap_reserve_limit_default(m, g):
        if m.gen_energy_source[g] == 'Solar':
            return 0.21288916
        elif m.gen_energy_source[g] == 'Wind':
            return 0.21624407
        else:
            raise RuntimeError()
    m.var_gen_cap_reserve_limit = Param(
        m.VARIABLE_GENS, 
        default=var_gen_cap_reserve_limit_default,
        doc="Maximum spinning reserves required, as fraction of installed capacity"
    )
    m.HawaiiVarGenUpSpinningReserveRequirement = Expression(
        m.BALANCING_AREA_TIMEPOINTS, 
        rule=lambda m, b, t: sum(
            m.GenCapacityInTP[g, t] 
            * min(
                m.var_gen_power_reserve[g] * m.gen_max_capacity_factor[g, t], 
                m.var_gen_cap_reserve_limit[g]
            )
            for g in m.VARIABLE_GENS
            if (g, t) in m.VARIABLE_GEN_TPS and b == m.zone_balancing_area[m.gen_load_zone[g]]),
        doc="The spinning reserves for backing up variable generation with Hawaii rules."
    )
    m.Spinning_Reserve_Up_Requirements.append('HawaiiVarGenUpSpinningReserveRequirement')

    def HawaiiLoadDownSpinningReserveRequirement_rule(m, b, t):
        if 'WithdrawFromCentralGrid' in dir(m):
            load = m.WithdrawFromCentralGrid
        else:
            load = m.lz_demand_mw
        return 0.10 * sum(load[z, t] for z in m.LOAD_ZONES if b == m.zone_balancing_area[z])
    m.HawaiiLoadDownSpinningReserveRequirement = Expression(
        m.BALANCING_AREA_TIMEPOINTS,
        rule=HawaiiLoadDownSpinningReserveRequirement_rule
    )
    m.Spinning_Reserve_Down_Requirements.append('HawaiiLoadDownSpinningReserveRequirement')


def nrel_3_5_spinning_reserve_requirements(m):
    """
    NREL35VarGenSpinningReserveRequirement[(b,t) in BALANCING_AREA_TIMEPOINTS]
    is an expression for upward and downward spinning reserve requirements of
    3% of load plus 5% of renewable output, based on a heuristic described in
    NREL's 2010 Western Wind and Solar Integration study. It is added to the
    Spinning_Reserve_Up_Requirements and Spinning_Reserve_Down_Requirements
    lists. If the local_td module is available with DER accounting, load will
    be set to WithdrawFromCentralGrid. Otherwise load will be set to
    lz_demand_mw.
    """
    def NREL35VarGenSpinningReserveRequirement_rule(m, b, t):
        if 'WithdrawFromCentralGrid' in dir(m):
            load = m.WithdrawFromCentralGrid
        else:
            load = m.lz_demand_mw
        return (0.03 * sum(load[z, t] for z in m.LOAD_ZONES
                           if b == m.zone_balancing_area[z])
              + 0.05 * sum(m.DispatchGen[g, t] for g in m.VARIABLE_GENS
                           if (g, t) in m.VARIABLE_GEN_TPS and 
                              b == m.zone_balancing_area[m.gen_load_zone[g]]))
    m.NREL35VarGenSpinningReserveRequirement = Expression(
        m.BALANCING_AREA_TIMEPOINTS, 
        rule=NREL35VarGenSpinningReserveRequirement_rule
    )
    m.Spinning_Reserve_Up_Requirements.append('NREL35VarGenSpinningReserveRequirement')
    m.Spinning_Reserve_Down_Requirements.append('NREL35VarGenSpinningReserveRequirement')


def define_components(m):
    """
    gen_can_provide_spinning_reserves[g] is a binary flag indicating whether
    the project is allowed to provide spinning reserves.
    
    AvailableGenSpinningReserveUp[(b,t) in BALANCING_AREA_TIMEPOINTS] is an 
    expression summarizing the amount of upward ramping capability from 
    generators within the balancing area, taking unit commitment into account.
    For now, this is simplified as the sum DispatchSlackUp.
    
    AvailableGenSpinningReserveDown[(b,t) in BALANCING_AREA_TIMEPOINTS] is a
    matching expression, but in the downward direction based on
    DispatchSlackDown.    
    """
    if m.options.unit_contigency:
        gen_unit_contigency(m)
    if m.options.project_contigency:
        gen_project_contigency(m)
    if m.options.spinning_requirement_rule == 'Hawaii':
        hawaii_spinning_reserve_requirements(m)
    elif m.options.spinning_requirement_rule == '3+5':
        nrel_3_5_spinning_reserve_requirements(m)
    
    
    m.contigency_safety_factor = Param(default=2.0,
        doc=("The spinning reserve requiremet will be set to this value "
             "times the maximum contigency. This defaults to 2 to ensure "
             "that the largest generator cannot be providing contigency "
             "reserves for itself."))
    m.gen_can_provide_spinning_reserves = Param(
        m.GENERATION_PROJECTS, within=Boolean, default=True
    )
    # Eventually, we may need something like GenCommitSpinningReservesUp[g,t]
    # and ...Down decision variables, but for the moment, just use the slack
    # variables to determine how much up and down ramping is available.
    m.AvailableGenSpinningReserveUp = Expression(
        m.BALANCING_AREA_TIMEPOINTS, 
        rule=lambda m, b, t: \
            sum(m.DispatchSlackUp[g, t] 
                for z in m.ZONES_IN_BALANCING_AREA[b]
                for g in m.GENS_IN_ZONE[z]
                if m.gen_can_provide_spinning_reserves[g] and 
                   t in m.TPS_FOR_GEN[g]
            )
    )
    m.Spinning_Reserve_Up_Provisions.append('AvailableGenSpinningReserveUp')

    m.AvailableGenSpinningReserveDown = Expression(
        m.BALANCING_AREA_TIMEPOINTS, 
        rule=lambda m, b, t: \
            sum(m.DispatchSlackDown[g, t] 
                for z in m.ZONES_IN_BALANCING_AREA[b]
                for g in m.GENS_IN_ZONE[z]
                if m.gen_can_provide_spinning_reserves[g] and 
                   t in m.TPS_FOR_GEN[g]
            )
    )
    m.Spinning_Reserve_Down_Provisions.append('AvailableGenSpinningReserveDown')
        

def define_dynamic_components(m):
    """    
    Satisfy_Spinning_Reserve_Up_Requirement[(b,t) in BALANCING_AREA_TIMEPOINTS]
    is a constraint that the sum of Spinning_Reserve_Up_Provisions is greater
    than or equal to the sum of Spinning_Reserve_Up_Requirements.

    Satisfy_Spinning_Reserve_Down_Requirement[(b,t) in BALANCING_AREA_TIMEPOINTS]
    is a matching constraint that uses the downward reserve lists.
    """
    m.MaximumContigency = Var(
        m.BALANCING_AREA_TIMEPOINTS,
        doc="Maximum of the registered Spinning_Reserve_Contigencies")
    for contigency in m.Spinning_Reserve_Contigencies:
        constraint_name = "Enforce_Max_Contigency_" + contigency
        constraint = Constraint(
            m.BALANCING_AREA_TIMEPOINTS,
            rule=lambda m, b, t: m.MaximumContigency[b, t] >= getattr(m, contigency)[b, t]
        )
        setattr(m, constraint_name, constraint)
    m.Spinning_Reserve_Up_Requirements.append('MaximumContigency')
    
    m.Satisfy_Spinning_Reserve_Up_Requirement = Constraint(
        m.BALANCING_AREA_TIMEPOINTS,
        rule=lambda m, b, t: \
            sum(getattr(m, requirement)[b,t]
                for requirement in m.Spinning_Reserve_Up_Requirements
            ) <= 
            sum(getattr(m, provision)[b,t]
                for provision in m.Spinning_Reserve_Up_Provisions
            )
    )
    m.Satisfy_Spinning_Reserve_Down_Requirement = Constraint(
        m.BALANCING_AREA_TIMEPOINTS,
        rule=lambda m, b, t: \
            sum(getattr(m, requirement)[b,t]
                for requirement in m.Spinning_Reserve_Down_Requirements
            ) <= 
            sum(getattr(m, provision)[b,t]
                for provision in m.Spinning_Reserve_Down_Provisions
            )
    )


# def load_inputs(m, switch_data, inputs_dir):
#   gen_can_provide_spinning_reserves[g]
#   contigency_safety_factor
#
#     switch_data.load_aug(
#         filename=os.path.join(inputs_dir, 'reserve_requirements.tab'),
#         auto_select=True,
#         param=(m.regulating_reserve_requirement_mw))
