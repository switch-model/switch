"""
This file provides the decorator post_process_step(msg)
which is a function decorator that ensures the post processing step is printed.
"""

from functools import wraps


def post_process_step(
    msg=None,
):
    """
    Decorator that should be used to register a post-processing step.

    @param msg The message to display while running this step.
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
