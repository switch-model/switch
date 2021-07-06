registered_post_process = []


def post_process():
    for func in registered_post_process:
        func()


def register_post_process(msg):
    def decorator(func):
        def wrapper():
            print(f"Post-process: {msg}...")
            func()

        registered_post_process.append(wrapper)
        return wrapper

    return decorator
