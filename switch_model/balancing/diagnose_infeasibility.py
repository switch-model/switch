"""
Relax constraints to help diagnose data problems in infeasible models

This module adds relaxation terms to all constraints in the model, which makes
every model feasible. It then minimizes the simple sum of the relaxation
variables (i.e., total violation of all constraints) instead of the normal cost
function. Then it report which constraints were violated and by how much.

Users can experiment by specifying `--no-relax` for some constraints, to find
out which constraints cannot be met on their own or cannot be met in combination
with other constraints (e.g., if specifying `--no-relax Constraint1` causes
`Constraint2` to be violated instead, then we know these are related. Then if
the model becomes infeasible when specifying `--no-relax Constraint1
Constraint2`, we know that Constraint1 and Constraint2 cannot be satisfied at
the same time. Users should then look for inconsistencies in the data used for
these two constraints.
"""

from switch_model.utilities import make_iterable
import pyomo.environ as pyo

relax_var_prefix = "Relax"
relax_var_dir = {1: "up", -1: "down"}

# TODO: look for a way to do all this from the pre_solve() step and in a more
# documented way. For example, deactivate all the existing constraints
# and create a new constraint list that has the relaxed versions of all of them,
# so we can work with the constructed constraints instead of the rules, and we
# can just check to see which deactivated constraints are violated after solving
# the model.

# Note: this module mostly doesn't distinguish between indexed and scalar
# constraints, but Pyomo generally presents scalar constraints as having an
# indexing set of [None], which can then be used as an index on the scalar
# variable, so it generally works out OK automatically.


def define_arguments(argparser):
    argparser.add_argument(
        "--no-relax",
        nargs="+",
        default=[],
        action="extend",
        help="Names of one or more constraints that should not be relaxed by "
        "the {} module. "
        "It is often helpful to solve once, observe contraints "
        "that are violated, then solve again without relaxing those "
        "constraints and observe which other constraints are violated "
        "instead. By repeating this process, you can identify a set of "
        "constraints that cannot all be satisfied simultaneously. "
        "(Note that this module never relaxes bounds on variables.)".format(__name__),
    )


def relaxable_constraints(m):
    for c in list(m.component_objects(pyo.Constraint)):
        if c.name not in m.options.no_relax:
            # skip the "--no-relax" constraints
            yield c


def define_dynamic_components(m):
    # convert bounds into constraints, which can then be relaxed along with the
    # other constraints
    for v in m.component_objects(pyo.Var):
        convert_bounds_to_constraint(m, v)

    # loop over an explicit list, otherwise the generator gets altered by the loop
    for c in list(relaxable_constraints(m)):
        # Define relaxation variables for all indices of this constraint
        # in both directions (up or down), so we can handle ==, <= or >=
        # constraints.
        # These variables are initialized as zero, since many of them will be
        # paired with Skip constraints and so never get sent to the solver.
        for direction in [1, -1]:
            var_name = relax_var_name(c, direction)
            relax_var = pyo.Var(
                c.index_set(), within=pyo.NonNegativeReals, initialize=0
            )
            setattr(m, var_name, relax_var)
            # Make sure the relaxation variable is constructed before the
            # constraint but after the constraint's indexing set. (This is why
            # we define different relaxation variables for every constraint,
            # instead of a single variable with indexes for all constraints.)
            move_component_above(relax_var, c)

        # relax the constraint
        relax_constraint(c)
        m.logger.info(f"relaxed constraint {c.name}")


def pre_solve(m):
    assign_relaxation_prices(m)


def post_solve(m, outputs_dir):
    # report any constraints that were violated
    unsatisfied_constraints = []
    for constraint in relaxable_constraints(m):
        constraint_name = constraint.name
        for key, c in constraint.items():
            for direction in [-1, 1]:
                # get the matching relaxation variable
                relax_var = getattr(m, relax_var_name(constraint, direction))
                val = relax_var[key].value
                if val is not None and val >= 1e-9:
                    # We could use name = c.name here, but it is slow to
                    # access constraints later in the model (see
                    # https://github.com/Pyomo/pyomo/issues/2560). Using repr()
                    # or str() on a list also gives a more copy-pastable
                    # representation of the constraint, which can be useful for
                    # debugging.
                    name = constraint_name
                    if key is not None:
                        name += repr(list(make_iterable(key)))
                    unsatisfied_constraints.append([name, direction * val])

    # We report results using logger.info, so users must set log-level to
    # info to see them. This is because these are diagnostic messages, not
    # errors, and because it prevents chatter from the test suite.
    if unsatisfied_constraints:
        for name, val in unsatisfied_constraints:
            m.logger.info("")
            m.logger.info(f"WARNING: Constraint {name} violated by {val:.4g} units.")
    else:
        m.logger.info(
            "\nCongratulations, the model is feasible. To obtain the optimal\n"
            f"solution, please solve again without using the {__name__} module."
        )

    m.logger.info(
        f"\nNOTE: Module {__name__} was used for this run.\n"
        "This minimizes violations of constraints, ignoring financial costs. Results from\n"
        "this run (other than constraint violations) should not be used for analysis.\n"
    )


def relax_var_name(constraint, direction):
    return "_".join(
        [
            relax_var_prefix,
            constraint.name,
            relax_var_dir[direction],
        ]
    )


def relax_constraint(c):
    def new_rule(m, *idx):
        # note: we use getattr(m, c.name) instead of just c, because
        # c is an object in the AbstractModel and this rule will be called on
        # a concrete instance.
        expr = getattr(m, c.name).original_rule(m, *idx)
        if expr is not pyo.Constraint.Skip and expr is not pyo.Constraint.Infeasible:
            if isinstance(expr, tuple):
                # constraint of type (lb, expr, ub) or (lb, var, ub)
                # add slack variables to the central expression
                lb, expr, ub = expr
                expr += sum(
                    direction * getattr(m, relax_var_name(c, direction))[idx]
                    for direction in [1, -1]
                )
                expr = (lb, expr, ub)
            else:
                # standard inequality constraint
                # pyomo provides a .args argument but it is not editable.
                # some versions provide ._args and some provide ._args_, so we use
                # what is available
                a = "_args" if hasattr(expr, "_args") else "_args_"
                args = list(getattr(expr, a))  # make mutable
                # add up and down relaxation vars to an arbitrary point in the
                # inequality (usually works out as high side)
                for direction in [1, -1]:
                    relax_var = getattr(m, relax_var_name(c, direction))
                    # next line uses idx if supplied, otherwise treats var as scalar
                    args[1] += direction * (relax_var[idx] if idx else relax_var)
                # convert back to original type
                setattr(expr, a, type(getattr(expr, a))(args))
        return expr

    # older versions of pyomo store the user's original rule function in the
    # `rule` attribute of the constraint, but newer versions (beginning sometime
    # between 5.4 and 6.4) convert the rule into a IndexedCallInitializer object.
    if hasattr(c.rule, "_fcn"):
        c.original_rule = c.rule._fcn
        c.rule._fcn = new_rule
    else:  # older Pyomo
        c.original_rule = c.rule
        c.rule = new_rule


def convert_bounds_to_constraint(m, v):
    """
    Relax upper and lower bounds on variables, if specified (will have no effect
    on inherent bounds like NonNegativeReals)
    """
    # At this point, the vars have all been defined but not yet constructed.

    # Store the original bounds rule and bypass it, then define a constraint
    # to enforce the bounds instead

    # older versions of Pyomo store the user's original bounds function in the
    # `_bounds_init_rule` attribute of the variable, but newer versions
    # (beginning sometime between 6.0 and 6.4) convert the rule into a
    # BoundInitializer object which contains a IndexedCallInitializer object,
    # which contains the rule in its _fcn attribute.
    try:
        if v._rule_bounds is None:
            return
        bounds_rule = v._rule_bounds._initializer._fcn
        v._rule_bounds = None
    except AttributeError:
        # older Pyomo (ending somewhere between 5.4 and 6.4)
        try:
            if v._bounds_init_rule is None:
                return
            bounds_rule = v._bounds_init_rule
            v._bounds_init_rule = None
        except AttributeError:
            # unexpected Pyomo behavior; let it pass but report it
            m.logger.error(f"ERROR: unable to determine bounds rule for {v.name}")
            return

    def constraint_rule(m, *idx):
        # note: we use getattr(m, v.name) instead of just v, because
        # v is an object in the AbstractModel and this rule will be called on
        # a concrete instance.
        var = getattr(m, v.name)[idx]
        lb, ub = bounds_rule(m, *idx)

        # This can work with None according to
        # https://pyomo.readthedocs.io/en/stable/pyomo_modeling_components/Constraints.html
        return (lb, var, ub)

        # # all possible constraint options, depending on presence of lower or
        # # upper bounds
        # options = {
        #     (True, True): lb <= var <= ub,
        #     (True, False): lb <= var,
        #     (False, True): var <= ub,
        #     (False, False): pyo.Constraint.Skip,
        # }
        # constraint = options[lb is not None, ub is not None]
        # return constraint

    # Add the bounds constraint to the model
    setattr(m, v.name + "_bounds", pyo.Constraint(v.index_set(), rule=constraint_rule))


def move_component_above(new_component, old_component):
    # move new component above old component within their parent block
    block = new_component.parent_block()
    if block is not old_component.parent_block():
        raise ValueError(
            "Cannot move component {} above {} because they are declared in different blocks.".format(
                new_component.name, old_component.name
            )
        )
    old_idx = block._decl[old_component.name]
    new_idx = block._decl[new_component.name]
    if new_idx < old_idx:
        # new_component is already above old_component
        return
    else:
        # reorder components
        # see https://groups.google.com/d/msg/pyomo-forum/dLbD2ly_hZo/5-INUaECNBkJ
        # remove all components from this block
        block_components = [c[0] for c in block._decl_order]
        # import pdb; pdb.set_trace()
        for c in block_components:
            if c is not None:
                block.del_component(c)
        # move the new component above the old one
        block_components.insert(old_idx, block_components.pop(new_idx))
        # add components back to the block
        for c in block_components:
            if c is not None:
                block.add_component(c.name, c)
        # the code below does the same thing, but seems a little too undocumented
        # new_cmp_entry = block._decl_order.pop(new_idx)
        # block._decl_order.insert(old_idx, new_cmp_entry)
        # # renumber block._decl to match new indexes
        # for i in range(old_idx, new_idx+1):
        #     block._decl[block._decl_order[i][0].name] = i


def assign_relaxation_prices(m):
    # Assign costs to the constraint relaxation variables
    def cost_rule(m):
        violations = []
        for constraint in relaxable_constraints(m):
            for direction in [1, -1]:
                var_name = relax_var_name(constraint, direction)
                for key, c in constraint.items():
                    var = getattr(m, var_name)[key]  # matching relaxation var
                    violations.append(var)
        return sum(violations)

    # note: we create a new objective function that ignores all the normal costs,
    # since we are focused only on minimizing constraint violations (possibly to
    # zero). Once it is feasible, the model should be re-solved without this
    # module to get a real solution. In principle we could use a high
    # multiplier on the violations and then add in the standard costs, but that
    # is not very useful and makes solutions much slower.
    m.Total_Constraint_Relaxations = pyo.Objective(rule=cost_rule, sense=pyo.minimize)
    m.Minimize_System_Cost.deactivate()
