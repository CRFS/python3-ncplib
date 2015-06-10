from enum import Enum, unique


PACKET_HEADER_SIZE = 32

PACKET_FIELD_HEADER_SIZE = 12

PACKET_PARAM_HEADER_SIZE = 8

PACKET_FOOTER_SIZE = 8


PACKET_HEADER_HEADER = b"\xdd\xcc\xbb\xaa"

PACKET_FOOTER_HEADER = b"\xaa\xbb\xcc\xdd"


@unique
class PacketFormat(Enum):

    standard = 1


@unique
class ParamType(Enum):

    string = 2
