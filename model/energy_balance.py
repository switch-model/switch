"""

Defines model components to describe bus-level energy balancing for the
SWITCH-Pyomo model.


SYNOPSIS
>>> from coopr.pyomo import *
>>> import utilities
>>> switch_modules = ('timescales', 'financials', 'load_zones', 'fuels',\
    'gen_tech', 'project_build', 'project_dispatch', 'trans_build',\
    'trans_dispatch', 'energy_balance')
>>> utilities.load_switch_modules(switch_modules)
>>> switch_model = utilities.define_AbstractModel(switch_modules)
>>> inputs_dir = 'test_dat'
>>> switch_data = utilities.load_data(switch_model, inputs_dir, switch_modules)
>>> switch_instance = switch_model.create(switch_data)

Note, this can be tested with `python -m doctest -v energy_balance.py`

Switch-pyomo is licensed under Apache License 2.0 More info at switch-model.org
"""

from coopr.pyomo import *
import utilities


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to enforce the
    first law of thermodynamics at the level of load zone busses. Unless
    otherwise stated, all terms describing power are in units of MW and
    all terms describing energy are in units of MWh.

    Satisfy_Load[load_zone, timepoint] is a constraint that mandates
    conservation of energy in every load zone and timepoint. This
    constraint sums the model components in the list
    LZ_Energy_Balance_components - each of which is indexed by (lz, t) -
    and ensures they are equal to lz_demand_mw[lz, t].

    # DEVELOPMENT NOTES

    In the future, I may move the definition of the Satisfy_Load
    constraint into a new method in the load_zones module, possibly
    named define_components_final() that would be called after all other
    modules had called define_components() and added their terms to the
    LZ_Energy_Balance_components list. However I organize it,
    Satisfy_Load has to be defined after all components that it
    references have been defined.

    """

    # This will add a min_data_check() method to the model
    utilities.add_min_data_check(mod)

    mod.Satisfy_Load = Constraint(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, lz, t: sum(
            getattr(m, compoment)[lz, t]
            for compoment in m.LZ_Energy_Balance_components
        ) == m.lz_demand_mw[lz, t])


def load_data(mod, switch_data, inputs_dir):
    """

    This empty function is included to provide a uniform interface. If
    you needed any data for energy balancing, you would import it
    here.

    """
