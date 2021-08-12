"""
This file provides two functions

1. register_post_process(msg, enabled=True) which is a function decorator that allows registering a function
as a post-process step.

2. run_post_process() which runs the registered post process steps.

These 2 functions are kept in a separate file to avoid cyclical dependencies.
"""

from functools import wraps
import functools

_registered_steps = {}


def register_post_process(
        msg=None,
):
    """
    Decorator that should be used to register a post-processing step.

    @param msg The message to display while running this step.
    @param enabled Whether we should be using this step.
    @param name Name of the post processing step and of the config section
    @param only_with_config if True the step will only run if 'name' exists in the config file
    @param priority 0 is highest priority (runs first) and larger numbers are lower priority.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            message = msg
            if message is None:
                message = f"Running {func.__name__}"
            print(f"\t{message}...")
            func(*args, **kwargs)
        return wrapper

    return decorator


def run_post_process(config, step_name=None):
    """
    Run the post processing steps.

    @param config The values from config.yaml (already parsed)
    @param step_name if step_name is None we run all the steps. If it's specified we only run that step.
    """
    if step_name is None:
        for name, func in sorted(_registered_steps.items(), key=lambda s: s[1].priority):
            func(config.get(name, None))
    else:
        _registered_steps[step_name](config.get(step_name, None))