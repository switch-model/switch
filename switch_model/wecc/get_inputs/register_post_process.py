"""
This file provides two functions

1. register_post_process(msg, enabled=True) which is a function decorator that allows registering a function
as a post-process step.

2. run_post_process() which runs the registered post process steps.

These 2 functions are kept in a separate file to avoid cyclical dependencies.
"""
import functools

_registered_steps = []


def register_post_process(
        name=None,
        msg=None,
        enabled=True,
        only_with_config=False,
        priority=2
):
    """
    Decorator that should be used to register a post-processing step.

    @param msg The message to display while running this step.
    @param enabled Whether we should be using this step.
    @param name Name of the post processing step and of the config section
    @param only_with_config if True the step will only run if 'name' exists in the config file
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(config=None):
            if only_with_config and config is None:
                return

            message = msg
            if message is None:
                message = f"Running {func.__name__}"

            print(f"\t{message}...")
            func(config)

        wrapper.name = name
        wrapper.priority = priority

        if enabled:
            _registered_steps.append(wrapper)
        return wrapper

    return decorator


def run_post_process(config):
    print("Post-processing...")

    for func in sorted(_registered_steps, key=lambda s: s.priority):
        if func.name is not None:
            func(config.get(func.name, None))
        else:
            func()
