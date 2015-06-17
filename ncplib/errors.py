from contextlib import contextmanager


__all__ = (
    "NCPError",
    "DecodeError",
    "NetworkError",
    "ClientError",
    "PacketError",
    "NCPWarning",
    "ClientWarning",
    "PacketWarning",
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
    except (OSError, EOFError) as ex:  # pragma: no cover
        raise NetworkError(str(ex)) from ex


class ClientError(NCPError):

    pass


class PacketError(ClientError):

    def __init__(self, packet_type, field_name, field_id, message, code):
        super().__init__(packet_type, field_name, field_id, message, code)
        self.packet_type = packet_type
        self.field_name = field_name
        self.field_id = field_id
        self.message = message
        self.code = code


# Warnings.

class NCPWarning(Warning):

    pass


class DecodeWarning(NCPWarning):

    pass


class ClientWarning(NCPWarning):

    pass


class PacketWarning(ClientWarning):

    def __init__(self, packet_type, field_name, field_id, message, code):
        super().__init__(packet_type, field_name, field_id, message, code)
        self.packet_type = packet_type
        self.field_name = field_name
        self.field_id = field_id
        self.message = message
        self.code = code
