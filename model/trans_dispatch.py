"""

Defines model components to describe transmission dispatch for the
SWITCH-Pyomo model.

SYNOPSIS
>>> from pyomo.environ import *
>>> import utilities
>>> switch_modules = ('timescales', 'financials', 'load_zones',\
    'trans_build', 'trans_dispatch')
>>> utilities.load_switch_modules(switch_modules)
>>> switch_model = utilities.define_AbstractModel(switch_modules)
>>> inputs_dir = 'test_dat'
>>> switch_data = utilities.load_data(switch_model, inputs_dir, switch_modules)
>>> switch_instance = switch_model.create(switch_data)

Note, this can be tested with `python -m doctest -v trans_dispatch.py`

Switch-pyomo is licensed under Apache License 2.0 More info at switch-model.org
"""

from pyomo.environ import *
import utilities


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe the
    dispatch of transmission resources in an electric grid. This
    includes parameters, dispatch decisions and constraints. Unless
    otherwise stated, all power capacity is specified in units of MW,
    all energy amounts are specified in units of MWh, and all sets and
    parameters are mandatory.

    TRANS_TIMEPOINTS describes the scope that transmission dispatch
    decisions must be made over. It is defined as the set of
    TRANS_DIRECTIONAL crossed with TIMEPOINTS. It is indexed as
    (load_zone_from, load_zone_to, timepoint) and may be abbreviated as
    [lz_from, lz_to, tp] for brevity.

    DispatchTrans[lz_from, lz_to, tp] is the decision of how much power
    to send along each transmission line in a particular direction in
    each timepoint.

    Maximum_DispatchTrans is a constraint that forces DispatchTrans to
    stay below the bounds of installed capacity.

    TxPowerSent[lz_from, lz_to, tp] is an expression that describes the
    power sent down a transmission line. This is completely determined by
    DispatchTrans[lz_from, lz_to, tp].

    TxPowerReceived[lz_from, lz_to, tp] is an expression that describes the
    power sent down a transmission line. This is completely determined by
    DispatchTrans[lz_from, lz_to, tp] and trans_efficiency[tx].

    LZ_TXNet[lz, tp] is an expression that returns the net power from
    transmission for a load zone. This is the sum of TxPowerReceived by
    the load zone minus the sum of TxPowerSent by the load zone.

    """

    # This will add a min_data_check() method to the model
    utilities.add_min_data_check(mod)

    mod.TRANS_TIMEPOINTS = Set(
        dimen=3,
        initialize=lambda m: m.TRANS_DIRECTIONAL * m.TIMEPOINTS
    )
    mod.DispatchTrans = Var(mod.TRANS_TIMEPOINTS, within=NonNegativeReals)

    mod.Maximum_DispatchTrans = Constraint(
        mod.TRANS_TIMEPOINTS,
        rule=lambda m, lz_from, lz_to, tp: (
            m.DispatchTrans[lz_from, lz_to, tp] <=
            m.TransCapacityAvailable[m.trans_d_line[lz_from, lz_to],
                                     m.tp_period[tp]]))

    mod.TxPowerSent = Expression(
        mod.TRANS_TIMEPOINTS,
        initialize=lambda m, lz_from, lz_to, tp: (
            m.DispatchTrans[lz_from, lz_to, tp]))
    mod.TxPowerReceived = Expression(
        mod.TRANS_TIMEPOINTS,
        initialize=lambda m, lz_from, lz_to, tp: (
            m.DispatchTrans[lz_from, lz_to, tp] *
            m.trans_efficiency[m.trans_d_line[lz_from, lz_to]]))

    def LZ_TXNet_calculation(m, lz, tp):
        return (
            sum(m.TxPowerReceived[lz_from, lz_to, tp]
                for (lz_from, lz_to, tp) in m.TRANS_TIMEPOINTS
                if lz_to == lz) -
            sum(m.TxPowerSent[lz_from, lz_to, tp]
                for (lz_from, lz_to, tp) in m.TRANS_TIMEPOINTS
                if lz_from == lz))
    mod.LZ_TXNet = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        initialize=LZ_TXNet_calculation)
    # Register net transmission as contributing to a load zone's energy
    mod.LZ_Energy_Balance_components.append('LZ_TXNet')


def load_data(mod, switch_data, inputs_dir):
    """

    This empty function is included to provide a uniform interface. If
    you needed any data for transmission dispatch, you would import it
    here. If you want to include seasonal adjustments of transfer
    capacity, this would be the place to import those parameters.

    """
