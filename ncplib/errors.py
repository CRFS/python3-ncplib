class Error(Exception):

    """
    Base class for all NCP errors.
    """


class DecodeError(Error):

    """
    An error was detected in the NCP packet.
    """
