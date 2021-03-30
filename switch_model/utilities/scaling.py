"""
Provides the classes and functions needed to support
variable scaling in pyomo.

TODO Explain variable scaling
"""

from pyomo.core import Var, Expression

# Setting this to False will disable scaling throughout SWITCH
_ENABLE_SCALING = True


class ScaledVariable:
    """
    Can be used the same way as pyomo's Var()
    however now we can pass in an additional parameter named 'scaling_factor'
    that will scale the variable automatically.
    """

    def __new__(cls, *args, scaling_factor=1, **kwargs):
        # If scaling is enabled and scaling_factor is not 1
        # return an instance of _ScaledVariable
        if _ENABLE_SCALING and scaling_factor != 1:
            return _ScaledVariable(*args, scaling_factor=scaling_factor, **kwargs)
        # Otherwise return an instance of pyomo's normal Var
        else:
            return Var(*args, **kwargs)
        # Note, we can't integrate _ScaledVariable into ScaledVariable
        # because pyomo will automatically replicate our object at which point
        # scaling_factor


class _ScaledVariable(Var):
    """
    Wraps pyomo's Var and adds support for a scaling_factor.

    Internally, when this object is assigned to the model,
    it gets assigned with a prefix "_scaled_" and an expression
    representing the unscaled variable is put in its place.
    """

    def __init__(self, *args, scaling_factor, bounds=None, **kwargs):
        self.args = args
        self.scaling_factor = scaling_factor
        self.scaled_name = None  # Gets set later by _AbstractModel

        if bounds is None:
            scaled_bounds = None
        else:
            # If the bounds are not None then we need to scale the bounds
            # The bounds are a function that return a tuple with the bound values
            # So we make a wrapper function that when called will call the original bound
            # then scale the bound values and return the scaled bound values
            def bound_scaling_wrapper(*bound_args):
                # Get the original bounds
                lower_bound, upper_bound = bounds(*bound_args)
                # Scale the bounds that are not None
                if lower_bound is not None:
                    lower_bound *= scaling_factor
                if upper_bound is not None:
                    upper_bound *= scaling_factor
                return lower_bound, upper_bound

            scaled_bounds = bound_scaling_wrapper

        # Initialize the variable with the scaled bounds
        super().__init__(*args, bounds=scaled_bounds, **kwargs)


def _get_unscaled_expression(scaled_var: _ScaledVariable, **kwargs):
    """
    Given a _ScaledVariable, return an Expression that equals the unscaled variable.

    The returned Expression will also have the attribute 'scaled_var_name' which is the
    name of the matching scaled variable.
    """
    scaled_var_name = scaled_var.scaled_name

    def unscaled_expression_rule(m, *inner_args):
        """
        The rule that is called when retrieving the value of the expression.
        Is equal to the value of the variable dividing by the scaling factor
        as this "undoes" the scaling. We want to undo the scaling
        because this expression should equal the unscaled variable.
        """
        v = getattr(m, scaled_var_name)
        return v[inner_args] / v.scaling_factor

    unscaled_expr = Expression(
        *scaled_var.args, rule=unscaled_expression_rule, **kwargs
    )
    unscaled_expr.scaled_var_name = scaled_var_name
    return unscaled_expr


def get_assign_default_value_rule(
    variable_name: str, default_value_parameter_name: str
):
    """
    Returns a rule that sets a default value for a variable.

    @param variable_name: The name of the variable whose default should be set (as a string)
    @param default_value_parameter_name: The name of the parameter that stores the default values (as a string)
    @returns A rule that can be passed to a BuildAction(..., rule=<>) object.

    Example:

    mod.BuildGen_assign_default_value = BuildAction(
        mod.PREDETERMINED_GEN_BLD_YRS,
        rule=rule_assign_default_value("BuildGen", "gen_predetermined_cap")
    )

    The code above will iterate over BuildGen for all the elements in
    PREDETERMINED_GEN_BLD_YRS and will set BuildGen's default value
    to the respective value in gen_predetermined_cap.
    """

    def rule(m, *args):
        """
        The rule that is returned by the parent function.
        This inner function is called by pyomo when pyomo runs the rule.
        """
        # First retrieve the variable we want to set a default value for
        variable_to_set = getattr(m, variable_name)
        # Then retrieve the default value
        default_value = getattr(m, default_value_parameter_name)[args]

        # If the variable has the attribute, then we need to make two changes.
        if hasattr(variable_to_set, "scaled_var_name"):
            # First the default needs to be set on the _ScaledVariable not
            # the unscaled expression.
            variable_to_set = getattr(m, variable_to_set.scaled_var_name)
            # Second the default value needs to be scaled accordingly.
            default_value *= variable_to_set.scaling_factor

        # Set the variable to the default value
        variable_to_set[args] = default_value

    return rule
