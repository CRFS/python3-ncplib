__all__ = (
    "DecodeError",
    "CommandError",
    "DecodeWarning",
    "CommandWarning",
)


class CommandMixin:

    def __init__(self, message, detail, code):
        super().__init__("Command error in {packet_type} {field_name} '{detail}' (code {code})".format(
            packet_type=message.packet.type,
            field_name=message.field.name,
            detail=detail,
            code=code,
        ))
        self.message = message
        self.detail = detail
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
