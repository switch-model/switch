from pyomo.environ import Suffix, TransformationFactory
import time

def scale(model):
    model.scaling_factor = Suffix(direction=Suffix.LOCAL)
    model.scaling_factor[model.Minimize_System_Cost] = 10**-8

    print("Transforming starting at {}".format(time.time()))
    scaled_model = TransformationFactory('core.scale_model').create_using(model)
    del scaled_model.scaling_factor
    print("Done at {}".format(time.time()))
    return scaled_model, model


def unscale(model, unscaled_model):
    TransformationFactory("core.scale_model").propagate_solution(model, unscaled_model)
    return unscaled_model
