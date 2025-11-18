HANDLER_REGISTRY = {}


def register_handler(role_name: str):
    """
    Decorador para registrar handlers de roles.
    """
    def decorator(func):
        HANDLER_REGISTRY[role_name.lower()] = func
        return func
    return decorator


def get_handler(role_name: str):
    return HANDLER_REGISTRY.get(role_name.lower())