from contextlib import contextmanager


__all__ = (
    "NCPError",
    "DecodeError",
    "NetworkError",
    "ClientError",
    "CommandError",
    "NCPWarning",
    "ClientWarning",
    "CommandWarning",
)


# Errors.

class NCPError(Exception):

    pass


class DecodeError(NCPError):

    pass


class NetworkError(NCPError):

    pass


@contextmanager
def wrap_network_errors():
    try:
        yield
    except (OSError, EOFError) as ex:
        raise NetworkError from ex


class ClientError(NCPError):

    pass


class CommandError(ClientError):

    def __init__(self, message, code, field):
        super().__init__(message, code, field)
        self.message = message
        self.code = code
        self.field = field


# Warnings.

class NCPWarning(Warning):

    pass


class ClientWarning(NCPWarning):

    pass


class CommandWarning(ClientWarning):

    def __init__(self, message, code, field):
        super().__init__(message, code, field)
        self.message = message
        self.code = code
        self.field = field
