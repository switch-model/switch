"""

Defines model components to describe bus-level energy balancing for the
SWITCH-Pyomo model.


SYNOPSIS
>>> import switch_mod.utilities as utilities
>>> switch_modules = ('timescales', 'financials', 'load_zones', 'local_td',\
    'fuels', 'gen_tech', 'project.build', 'project.dispatch',\
    'trans_build', 'trans_dispatch', 'energy_balance')
>>> utilities.load_modules(switch_modules)
>>> switch_model = utilities.define_AbstractModel(switch_modules)
>>> inputs_dir = 'test_dat'
>>> switch_data = utilities.load_data(switch_model, inputs_dir, switch_modules)
>>> switch_instance = switch_model.create(switch_data)

Note, this can be tested by running `python -m doctest energy_balance.py`
within the switch_mod source directory.

Switch-pyomo is licensed under Apache License 2.0 More info at switch-model.org
"""

from pyomo.environ import *


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to enforce the
    first law of thermodynamics at the level of load zone busses. Unless
    otherwise stated, all terms describing power are in units of MW and
    all terms describing energy are in units of MWh.

    Energy_Balance[load_zone, timepoint] is a constraint that mandates
    conservation of energy in every load zone and timepoint. This
    constraint sums the model components in the list
    LZ_Energy_Balance_components - each of which is indexed by (lz, t) -
    and ensures they sum to 0. By convention, energy production has a
    positive sign and energy consumption has a negative sign.

    # DEVELOPMENT NOTES

    In the future, I may move the definition of the Satisfy_Load
    constraint into a new method in the load_zones module, possibly
    named define_components_final() that would be called after all other
    modules had called define_components() and added their terms to the
    LZ_Energy_Balance_components list. However I organize it,
    Satisfy_Load has to be defined after all components that it
    references have been defined.

    """

    mod.Energy_Balance = Constraint(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, lz, t: sum(
            getattr(m, compoment)[lz, t]
            for compoment in m.LZ_Energy_Balance_components
        ) == 0)


def load_data(mod, switch_data, inputs_dir):
    """

    This empty function is included to provide a uniform interface. If
    you needed any data for energy balancing, you would import it
    here.

    """
