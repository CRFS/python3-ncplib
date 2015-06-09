from enum import Enum, unique


@unique
class PacketFormat(Enum):

    standard = 1


@unique
class ParamType(Enum):

    string = 2
