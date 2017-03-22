"""Minimize excess renewable production (dissipated in transmission losses) and 
smooth out demand response and EV charging as much as possible."""

from pyomo.environ import *

def define_components(m):
    if m.options.solver in ('cplex', 'cplexamp', 'gurobi'):
        m.options.smooth_dispatch = True
    else:
        # glpk and cbc can't handle quadratic problem used for smoothing
        m.options.smooth_dispatch = False
        if m.options.verbose:
            print "Not smoothing dispatch because {} cannot solve a quadratic model.".format(m.options.solver)
            print "Remove hawaii.smooth_dispatch from modules.txt and iterate.txt to avoid this message."

    # add an alternative objective function that smoothes out various non-cost variables
    if m.options.smooth_dispatch:
        def Smooth_Free_Variables_obj_rule(m):
            # minimize production (i.e., maximize curtailment / minimize losses)
            obj = sum(
                getattr(m, component)[z, t] 
                    for z in m.LOAD_ZONES 
                        for t in m.TIMEPOINTS 
                            for component in m.LZ_Energy_Components_Produce)
            # minimize the variability of various slack responses
            adjustable_components = [
                'ShiftDemand', 'ChargeBattery', 'DischargeBattery', 'ChargeEVs', 
                'RunElectrolyzerMW', 'LiquifyHydrogenMW', 'DispatchFuelCellMW'
            ]
            for var in adjustable_components:
                if hasattr(m, var):
                    if m.options.verbose:
                        print "Will smooth {}.".format(var)
                    comp = getattr(m, var)
                    obj += sum(comp[z, t]*comp[z, t] for z in m.LOAD_ZONES for t in m.TIMEPOINTS)
            return obj
        m.Smooth_Free_Variables = Objective(rule=Smooth_Free_Variables_obj_rule, sense=minimize)

def pre_iterate(m):
    if m.options.smooth_dispatch:
        if m.iteration_number == 0:
            # make sure the minimum-cost objective is in effect
            m.Smooth_Free_Variables.deactivate()
            m.Minimize_System_Cost.activate()
        elif m.iteration_number == 1:
            # switch to the smoothing objective
            fix_obj_expression(m.Minimize_System_Cost)
            m.Minimize_System_Cost.deactivate()
            m.Smooth_Free_Variables.activate()
            print "smoothing free variables..."
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
        if hasattr(m, "dual"):
            if m.iteration_number == 0:
                # save dual values  for later use (solving with a different objective
                # will alter them in an undesirable way)
                m.old_dual_dict = m.dual._dict.copy()
            else:
                # restore duals from the original solution
                m.dual._dict = m.old_dual_dict

        # setup model for next iteration
        if m.iteration_number == 0:
            done = False # we'll have to run again to do the smoothing
        elif m.iteration_number == 1:
            # finished smoothing the model
            # restore the standard objective
            m.Smooth_Free_Variables.deactivate()
            m.Minimize_System_Cost.activate()
            # unfix the variables
            fix_obj_expression(m.Minimize_System_Cost, False)
            # now we're done
            done = True
        else:
            raise RuntimeError("Reached unexpected iteration number {} in module {}.".format(m.iteration_number, __name__))
    else:
        # not smoothing the dispatch
        done = True

    return done

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
        fix_obj_expression(e.exg, status)
    elif hasattr(e, 'is_constant') and e.is_constant():
        pass    # numeric constant
    else:
        raise ValueError(
            'Expression {e} does not have an exg, fixed or _args property, ' +
            'so it cannot be fixed.'.format(e=e)
        )
        

