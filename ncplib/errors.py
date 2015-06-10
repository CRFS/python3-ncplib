class Error(Exception):

    """
    Base class for all NCP errors.
    """


class DecodeError(Error):

    """
    An error occured while decoding an NCP packet.
    """
