"""Minimize excess renewable production (dissipated in transmission losses) and
smooth out demand response and EV charging as much as possible."""

from pyomo.environ import *
import switch_model.solve

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
        if hasattr(m, 'ChargeEVs') and isinstance(m.ChargeEVs, Expression):
            # Create a variable bound to the ChargeEVs expression
            # that can be squared in the objective function without creating
            # a non-positive-definite problem.
            m.ChargeEVsVar = Var(m.ChargeEVs.index_set())
            m.ChargeEVsVar_fix = Constraint(
                m.ChargeEVs.index_set(),
                rule=lambda m, *key: m.ChargeEVsVar[key] == m.ChargeEVs[key]
            )

        def Smooth_Free_Variables_obj_rule(m):
            # minimize production (i.e., maximize curtailment / minimize losses)
            obj = sum(
                getattr(m, component)[z, t]
                    for z in m.LOAD_ZONES
                        for t in m.TIMEPOINTS
                            for component in m.Zone_Power_Injections)

            # minimize the variability of various slack responses
            components_to_smooth = [
                'ShiftDemand', 'ChargeBattery', 'DischargeBattery',
                'RunElectrolyzerMW', 'LiquifyHydrogenMW', 'DispatchFuelCellMW',
            ]
            if hasattr(m, 'ChargeEVsVar'):
                components_to_smooth.append('ChargeEVsVar')
            else:
                components_to_smooth.append('ChargeEVs')

            for var in components_to_smooth:
                if hasattr(m, var):
                    if m.options.verbose:
                        print "Will smooth {}.".format(var)
                    comp = getattr(m, var)
                    obj += sum(comp[z, t]*comp[z, t] for z in m.LOAD_ZONES for t in m.TIMEPOINTS)
            # include standard storage generators too
            if hasattr(m, 'STORAGE_GEN_TPS'):
                print "Will smooth charging and discharging of standard storage."
                obj += sum(m.ChargeStorage[g, tp]*m.ChargeStorage[g, tp] for g, tp in m.STORAGE_GEN_TPS)
                obj += sum(m.DispatchGen[g, tp]*m.DispatchGen[g, tp] for g, tp in m.STORAGE_GEN_TPS)
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
            return obj
        m.Smooth_Free_Variables = Objective(rule=Smooth_Free_Variables_obj_rule, sense=minimize)
        # leave standard objective in effect for now
        m.Smooth_Free_Variables.deactivate()

        # def Fix_Obj_rule(m):
        #     # import pdb; pdb.set_trace()
        #     # make sure the minimum-cost objective is in effect
        #     # not sure if this is needed, and not sure
        #     m.Smooth_Free_Variables.deactivate()
        #     m.Minimize_System_Cost.activate()
        # m.Fix_Obj = BuildAction(rule=Fix_Obj_rule)

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
        switch_model.solve.solve(m)
        post_smooth_solve(m)

def pre_smooth_solve(m):
    """ store model state and prepare for smoothing """
    save_duals(m)
    fix_obj_expression(m.Minimize_System_Cost)
    m.Minimize_System_Cost.deactivate()
    m.Smooth_Free_Variables.activate()
    print "smoothing free variables..."

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
    if hasattr(e, 'fixed'):
        e.fixed = status      # see p. 171 of the Pyomo book
    elif hasattr(e, '_numerator'):
        for e2 in e._numerator:
            fix_obj_expression(e2, status)
        for e2 in e._denominator:
            fix_obj_expression(e2, status)
    elif hasattr(e, '_args'):
        for e2 in e._args:
            fix_obj_expression(e2, status)
    elif hasattr(e, 'expr'):
        fix_obj_expression(e.expr, status)
    elif hasattr(e, 'is_constant'):
        # parameter; we don't actually care if it's mutable or not
        pass
    else:
        raise ValueError(
            'Expression {e} does not have an exg, fixed or _args property, ' +
            'so it cannot be fixed.'.format(e=e)
        )
