from functools import wraps


def valuedispatch(func):
    registry = {}

    def register(value, func=None):
        def decorator(func):
            registry[value] = func
            return func
        return decorator

    @wraps(func)
    def do_valuedispatch(arg1, *args, **kwargs):
        return registry.get(arg1, func)(arg1, *args, **kwargs)

    do_valuedispatch.registry = registry
    do_valuedispatch.register = register
    return do_valuedispatch
