__all__ = (
    "DecodeError",
    "CommandError",
    "DecodeWarning",
    "CommandWarning",
)


class CommandMixin:

    def __init__(self, packet_type, field_name, message, code):
        super().__init__(packet_type, field_name, message, code)
        self.packet_type = packet_type
        self.field_name = field_name
        self.message = message
        self.code = code


# Errors.

class DecodeError(Exception):

    pass


class CommandError(CommandMixin, Exception):

    pass


# Warnings.

class DecodeWarning(Warning):

    pass


class CommandWarning(CommandMixin, Warning):

    pass
