"""
This file provides two functions

1. register_post_process(msg, enabled=True) which is a function decorator that allows registering a function
as a post-process step.

2. run_post_process() which runs the registered post process steps.

These 2 functions are kept in a separate file to avoid cyclical dependencies.
"""
_registered_steps = []


def register_post_process(msg, enabled=True):
    """
    Decorator that should be used to register a post-processing step.

    @param msg The message to display while running this step.
    @param enabled Whether we should be using this step.
    """
    def decorator(func):
        def wrapper():
            print(f"\t{msg}...")
            func()

        if enabled:
            _registered_steps.append(wrapper)
        return wrapper

    return decorator

def run_post_process():
    print("Post-processing...")
    for func in _registered_steps:
        func()