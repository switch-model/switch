from pyomo.environ import Suffix, TransformationFactory
import time

from switch_model.utilities import StepTimer

"""
Offers two functions scale() and unscale() to ensure
constants and variables are within a reasonable range.
Used when the --wecc-scale flag is used.
"""

def scale(model):
    step_timer = StepTimer()
    print("Scaling variables...")

    model.scaling_factor = Suffix(direction=Suffix.LOCAL)
    model.scaling_factor[model.Minimize_System_Cost] = 10**-9


    scaled_model = TransformationFactory('core.scale_model').create_using(model)
    del scaled_model.scaling_factor

    print("Done scaling in {} s".format(step_timer.step_time()))

    return scaled_model, model


def unscale(model, unscaled_model):
    TransformationFactory("core.scale_model").propagate_solution(model, unscaled_model)
    return unscaled_model
