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

    i32 = 0x00

    u32 = 0x01

    string = 0x02

    raw = 0x80

    u8array = 0x81

    u16array = 0x82

    u32array = 0x83

    i8array = 0x84

    i16array = 0x85

    i32array = 0x86
