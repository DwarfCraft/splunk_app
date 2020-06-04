
class MissingArgumentError(ValueError):
    def __init__(self, message):
        super(ValueError, self).__init__(message)
        self.message = message


def required_kwargs(*req_args):
    """
    :param req_args: a series of required argument names, must be strings
    :return: a decorator for a function that will validate the presence of req_args in **kwargs
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            for var in req_args:
                if not kwargs.has_key(var):
                    raise MissingArgumentError('required arg {} is missing'.format(var))
            func(*args, **kwargs)
        return wrapper
    return decorator
