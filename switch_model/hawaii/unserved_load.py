"""Add an UnservedLoad component, which ensures the model is always feasible.
This is often useful when the model is constrained to the edge of infeasibility,
(e.g., when evaluating a pre-defined, just-feasible construction plan) to avoid
spurious reports of infeasibility."""
from pyomo.environ import *


def define_arguments(argparser):
    argparser.add_argument(
        "--unserved-load-penalty",
        type=float,
        default=None,
        help="Penalty to charge per MWh of unserved load. Usually set high enough to force unserved load to zero (default is $10,000/MWh).",
    )


def define_components(m):
    # create an unserved load variable with a high penalty cost,
    # to avoid infeasibilities when
    # evaluating scenarios that are on the edge of infeasibility
    # cost per MWh for unserved load (high)
    if m.options.unserved_load_penalty is not None:
        # always use penalty factor supplied on the command line, if any
        m.unserved_load_penalty_per_mwh = Param(
            within=NonNegativeReals, initialize=m.options.unserved_load_penalty
        )
    else:
        # no penalty on the command line, use whatever is in the parameter files, or 10000
        m.unserved_load_penalty_per_mwh = Param(within=NonNegativeReals, default=10000)

    # amount of unserved load during each timepoint
    m.UnservedLoad = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    # total cost for unserved load
    m.UnservedLoadPenalty = Expression(
        m.TIMEPOINTS,
        rule=lambda m, tp: m.tp_duration_hrs[tp]
        * sum(
            m.UnservedLoad[z, tp] * m.unserved_load_penalty_per_mwh
            for z in m.LOAD_ZONES
        ),
    )
    # add the unserved load to the model's energy balance
    m.Zone_Power_Injections.append("UnservedLoad")
    # add the unserved load penalty to the model's objective function
    m.Cost_Components_Per_TP.append("UnservedLoadPenalty")

    # amount of unserved reserves during each timepoint
    m.UnservedUpReserves = Var(m.TIMEPOINTS, within=NonNegativeReals)
    m.UnservedDownReserves = Var(m.TIMEPOINTS, within=NonNegativeReals)
    # total cost for unserved reserves (90% as high as cost of unserved load,
    # to make the model prefer to serve load when possible)
    m.UnservedReservePenalty = Expression(
        m.TIMEPOINTS,
        rule=lambda m, tp: m.tp_duration_hrs[tp]
        * 0.9
        * m.unserved_load_penalty_per_mwh
        * (m.UnservedUpReserves[tp] + m.UnservedDownReserves[tp]),
    )
    # add the unserved load penalty to the model's objective function
    m.Cost_Components_Per_TP.append("UnservedReservePenalty")
