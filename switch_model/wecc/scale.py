from pyomo.environ import Suffix, TransformationFactory
import time

from switch_model.utilities import StepTimer

"""
Offers two functions scale() and unscale() to ensure
constants and variables are within a reasonable range.
Used when the --wecc-scale flag is used.
"""

def scale(model):
    timer = StepTimer()
    print("Scaling variables...")

    model.scaling_factor = Suffix(direction=Suffix.LOCAL)
    model.scaling_factor[model.Minimize_System_Cost] = 10**-7
    model.scaling_factor[model.BuildGen] = 10**-3
    model.scaling_factor[model.ConsumeFuelTier] = 10**-4
    model.scaling_factor[model.DispatchGen] = 10**-2
    model.scaling_factor[model.RPS_Enforce_Target] = 10**-5


    scaled_model = TransformationFactory('core.scale_model').create_using(model)
    del scaled_model.scaling_factor

    print("Done scaling in {:2f} s".format(timer.step_time()))

    return scaled_model, model


def unscale(model, unscaled_model):
    timer = StepTimer()
    print("Unscaling variables...")
    TransformationFactory("core.scale_model").propagate_solution(model, unscaled_model)
    print("Done unscaling in {:2f} s".format(timer.step_time()))
    return unscaled_model
