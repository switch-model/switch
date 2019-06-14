"""Minimize excess renewable production (dissipated in transmission and battery
losses) and smooth out demand response and EV charging as much as possible."""

from pyomo.environ import *
from pyomo.core.base.numvalue import native_numeric_types
import switch_model.solve
from switch_model.utilities import iteritems

def define_components(m):
    if m.options.solver in ('cplex', 'cplexamp', 'gurobi', 'gurobi_ampl'):
        m.options.smooth_dispatch = True
    else:
        # glpk and cbc can't handle quadratic problem used for smoothing
        m.options.smooth_dispatch = False
        if m.options.verbose:
            print "Not smoothing dispatch because {} cannot solve a quadratic model.".format(m.options.solver)
            print "Remove hawaii.smooth_dispatch from modules.txt and iterate.txt to avoid this message."

    # add an alternative objective function that smoothes out time-shiftable energy sources and sinks
    if m.options.smooth_dispatch:
        # minimize the range of variation of various slack responses;
        # these should each have timepoint as their final index component
        components_to_smooth = [
            'ShiftDemand', 'ChargeBattery', 'DischargeBattery', 'ChargeEVs',
            'RunElectrolyzerMW', 'LiquifyHydrogenMW', 'DispatchFuelCellMW',
            'DispatchGen', 'ChargeStorage',
        ]

        def add_smoothing_entry(m, d, component, key):
            """
            Add an entry to the dictionary d of elements to smooth. The entry's
            key is based on component name and specified key, and its value is
            an expression whose absolute value should be minimized to smooth the
            model. The last element of the provided key must be a timepoint, and
            the expression is equal to the value of the component at this
            timepoint minus its value at the previous timepoint.
            """
            tp = key[-1]
            prev_tp = m.TPS_IN_TS[m.tp_ts[tp]].prevw(tp)
            entry_key = str((component.name,) + key)
            entry_val = component[key] - component[key[:-1]+(prev_tp,)]
            d[entry_key] = entry_val

        def rule(m):
            m.component_smoothing_dict = dict()
            """Find all components to be smoothed"""
            # smooth named components
            for c in components_to_smooth:
                try:
                    comp = getattr(m, c)
                except AttributeError:
                    continue
                print "Will smooth {}.".format(c)
                for key in comp:
                    add_smoothing_entry(m, m.component_smoothing_dict, comp, key)
            # # smooth standard storage generators
            # if hasattr(m, 'STORAGE_GEN_TPS'):
            #     print "Will smooth charging and discharging of standard storage."
            #     for c in ['ChargeStorage', 'DispatchGen']:
            #         comp = getattr(m, c)
            #         for key in m.STORAGE_GEN_TPS:
            #             add_smoothing_entry(m, m.component_smoothing_dict, comp, key)
        m.make_component_smoothing_dict = BuildAction(rule=rule)

        # Force IncreaseSmoothedValue to equal any step-up in a smoothed value
        m.ISV_INDEX = Set(initialize=lambda m: m.component_smoothing_dict.keys())
        m.IncreaseSmoothedValue = Var(m.ISV_INDEX, within=NonNegativeReals)
        m.Calculate_IncreaseSmoothedValue = Constraint(
            m.ISV_INDEX,
            rule=lambda m, k: m.IncreaseSmoothedValue[k] >= m.component_smoothing_dict[k]
        )

        def Smooth_Free_Variables_obj_rule(m):
            # minimize production (i.e., maximize curtailment / minimize losses)
            obj = sum(
                getattr(m, component)[z, t]
                    for z in m.LOAD_ZONES
                        for t in m.TIMEPOINTS
                            for component in m.Zone_Power_Injections)
            # also maximize up reserves, which will (a) minimize arbitrary burning off of renewables
            # (e.g., via storage) and (b) give better representation of the amount of reserves actually available
            if hasattr(m, 'Spinning_Reserve_Up_Provisions') and hasattr(m, 'GEN_SPINNING_RESERVE_TYPES'): # advanced module
                print "Will maximize provision of up reserves."
                reserve_weight = {'contingency': 0.9, 'regulation': 1.1}
                for comp_name in m.Spinning_Reserve_Up_Provisions:
                    component = getattr(m, comp_name)
                    obj += -0.1 * sum(
                        reserve_weight.get(rt, 1.0) * component[rt, ba, tp]
                        for rt, ba, tp in component
                    )
            # minimize absolute value of changes in the smoothed variables
            obj += sum(v for v in m.IncreaseSmoothedValue.values())
            return obj
        m.Smooth_Free_Variables = Objective(rule=Smooth_Free_Variables_obj_rule, sense=minimize)

        # constrain smoothing objective to find unbounded ray
        m.Bound_Obj = Constraint(rule=lambda m: Smooth_Free_Variables_obj_rule(m) <= 1e9)

        # leave standard objective in effect for now
        m.Smooth_Free_Variables.deactivate()


def pre_iterate(m):
    if m.options.smooth_dispatch:
        if m.iteration_number == 0:
            # indicate that this was run in iterated mode, so no need for post-solve
            m.iterated_smooth_dispatch = True
        elif m.iteration_number == 1:
            pre_smooth_solve(m)
        else:
            raise RuntimeError("Reached unexpected iteration number {} in module {}.".format(m.iteration_number, __name__))

    return None  # no comment on convergence

def post_iterate(m):
    if hasattr(m, "ChargeBattery"):
        double_charge = [
            (
                z, t,
                m.ChargeBattery[z, t].value,
                m.DischargeBattery[z, t].value
            )
                for z in m.LOAD_ZONES
                    for t in m.TIMEPOINTS
                        if m.ChargeBattery[z, t].value > 0
                            and m.DischargeBattery[z, t].value > 0
        ]
        if len(double_charge) > 0:
            print ""
            print "WARNING: batteries are simultaneously charged and discharged in some hours."
            print "This is usually done to relax the biofuel limit."
            for (z, t, c, d) in double_charge:
                print 'ChargeBattery[{z}, {t}]={c}, DischargeBattery[{z}, {t}]={d}'.format(
                    z=z, t=m.tp_timestamp[t],
                    c=c, d=d
                )

    if m.options.smooth_dispatch:
        # setup model for next iteration
        if m.iteration_number == 0:
            done = False # we'll have to run again to do the smoothing
        elif m.iteration_number == 1:
            # finished smoothing the model
            post_smooth_solve(m)
            # now we're done
            done = True
        else:
            raise RuntimeError("Reached unexpected iteration number {} in module {}.".format(m.iteration_number, __name__))
    else:
        # not smoothing the dispatch
        done = True

    return done

def post_solve(m, outputs_dir):
    """ Smooth dispatch if it wasn't already done during an iterative solution. """
    if m.options.smooth_dispatch and not getattr(m, 'iterated_smooth_dispatch', False):
        pre_smooth_solve(m)
        # re-solve and load results
        m.preprocess()
        solve(m)
        post_smooth_solve(m)

def pre_smooth_solve(m):
    """ store model state and prepare for smoothing """
    save_duals(m)
    fix_obj_expression(m.Minimize_System_Cost)
    m.Minimize_System_Cost.deactivate()
    m.Smooth_Free_Variables.activate()
    print "smoothing free variables..."

def solve(m):
    try:
        switch_model.solve.solve(m)
    except RuntimeError as e:
        if e.message.lower() == 'infeasible model':
            # show a warning, but don't abort the overall post_solve process
            print('WARNING: model became infeasible when smoothing; reverting to original solution.')
        else:
            raise

def post_smooth_solve(m):
    """ restore original model state """
    # restore the standard objective
    m.Smooth_Free_Variables.deactivate()
    m.Minimize_System_Cost.activate()
    # unfix the variables
    fix_obj_expression(m.Minimize_System_Cost, False)
    # restore any duals from the original solution
    restore_duals(m)


def save_duals(m):
    if hasattr(m, 'dual'):
        m.old_dual_dict = m.dual._dict.copy()
    if hasattr(m, 'rc'):
        m.old_rc_dict = m.rc._dict.copy()

def restore_duals(m):
    if hasattr(m, 'dual'):
        m.dual._dict = m.old_dual_dict
    if hasattr(m, 'rc'):
        m.rc._dict = m.old_rc_dict

def fix_obj_expression(e, status=True):
    """Recursively fix all variables included in an objective expression."""
    # note: this contains code to work with various versions of Pyomo,
    # e.g., _potentially_variable in 5.1, is_potentially_variable in 5.6
    if hasattr(e, 'fixed'):
        e.fixed = status      # see p. 171 of the Pyomo book
    elif hasattr(e, '_numerator'):
        for e2 in e._numerator:
            fix_obj_expression(e2, status)
        for e2 in e._denominator:
            fix_obj_expression(e2, status)
    elif hasattr(e, 'args'):  # SumExpression; can't actually see where this is defined in Pyomo though
        for e2 in e.args:
            fix_obj_expression(e2, status)
    elif hasattr(e, '_args'): # switched to 'args' and/or '_args_' in Pyomo 5
        for e2 in e._args:
            fix_obj_expression(e2, status)
    elif hasattr(e, 'expr'):
        fix_obj_expression(e.expr, status)
    # below here are parameters or constants, no need to fix
    elif hasattr(e, 'is_potentially_variable') and not e.is_potentially_variable():
        pass
    elif hasattr(e, '_potentially_variable') and not e._potentially_variable():
        pass
    elif hasattr(e, 'is_constant') and e.is_constant():
        pass
    elif type(e) in native_numeric_types:
        pass
    else:
        raise ValueError(
            'Expression {} does not have an expr, fixed or args property, '
            'so it cannot be fixed.'.format(e)
        )
