__all__ = (
    "DecodeError",
    "CommandError",
    "DecodeWarning",
    "CommandWarning",
)


# Errors.

class DecodeError(Exception):

    pass


class CommandError(Exception):

    def __init__(self, packet_type, field_name, field_id, message, code):
        super().__init__(packet_type, field_name, field_id, message, code)
        self.packet_type = packet_type
        self.field_name = field_name
        self.field_id = field_id
        self.message = message
        self.code = code


class ConnectionClosed(EOFError):

    pass


# Warnings.

class DecodeWarning(Warning):

    pass


class CommandWarning(Warning):

    def __init__(self, packet_type, field_name, field_id, message, code):
        super().__init__(packet_type, field_name, field_id, message, code)
        self.packet_type = packet_type
        self.field_name = field_name
        self.field_id = field_id
        self.message = message
        self.code = code
