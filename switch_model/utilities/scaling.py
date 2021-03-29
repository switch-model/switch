"""
Provides the classes and functions needed to support
variable scaling in pyomo.

TODO Explain variable scaling
"""

from pyomo.core import Var, Expression

_ENABLE_SCALING = True


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
        """The rule that is returned by the parent function."""

        # This inner function is called by pyomo when pyomo runs the rule.
        # First retrieve the variable we want to set a default value for
        variable_to_set = getattr(m, variable_name)
        # Then retrieve the default value
        default_value = getattr(m, default_value_parameter_name)[args]

        # If the variable has the attribute, then we need to make two changes.
        if variable_to_set.scaled_var_name is not None:
            # First the default needs to be set on the ScaledVariable not
            # the UnscaledVariable. This is because the UnscaledVariable
            # is actually just an expression.
            variable_to_set = getattr(m, variable_to_set.scaled_var_name)
            # Second the default variable needs to be scaled accordingly.
            default_value *= variable_to_set.scaling_factor

        # Set the variable to the default value
        variable_to_set[args] = default_value

    return rule


class ScaledVariable(Var):
    def __init__(self, *args, scaling_factor=1, bounds=None, **kwargs):
        self.scaling_factor = scaling_factor
        self.args = args
        self.scaled_name = None  # Get set later by _AbstractModel

        if bounds is not None:
            # Create a function that returns the scaled bounds
            def bound_scaling_wrapper(*bound_args):
                lower_bound, upper_bound = bounds(*bound_args)
                if lower_bound is not None:
                    lower_bound *= scaling_factor
                if upper_bound is not None:
                    upper_bound *= scaling_factor
                return lower_bound, upper_bound

            scaled_bounds = bound_scaling_wrapper
        else:
            scaled_bounds = None

        # Initialize the variable with the scaled bounds
        super().__init__(*args, bounds=scaled_bounds, **kwargs)


def get_unscaled_variable(scaled_var: ScaledVariable, **kwargs):
    """
    Returns an instance of pyomo's Expression() representing
    an expression that is simply the variable scaled.

    The returned Expression object will also have the attribute
    'scaled_var_name'.
    """
    scaled_var_name = scaled_var.scaled_name

    def unscaled_variable_rule(m, *inner_args):
        v = getattr(m, scaled_var_name)
        return v[inner_args] / v.scaling_factor

    unscaled_var = Expression(*scaled_var.args, rule=unscaled_variable_rule, **kwargs)
    unscaled_var.scaled_var_name = scaled_var_name
    return unscaled_var
