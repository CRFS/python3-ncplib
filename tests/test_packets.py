import unittest
from array import array
from datetime import datetime, timezone
from ncplib.packets import decode_packet, encode_packet, PacketData, FieldData
from ncplib import uint


REAL_PACKET = (
    b"\xdd\xcc\xbb\xaaLINK'\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00s\xe9\x8eT(\x05\x1b&4I\xb4\x81HELO\x1d"
    b"\x00\x00\x00\x00\x00\x00\x00NCPV\x0f\x00\x00\x02Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__\x00"
    b"SEID\x04\x00\x00\x02monitor\x00MACA\x07\x00\x00\x0200:24:81:b4:49:34\x00\x00\x00\x00\x00\x00\x00\xaa\xbb"
    b"\xcc\xdd"
)


PACKET_VALUES = [
    # Integers.
    (-2 ** 31, -2 ** 31),
    (0, 0),
    (10, 10),
    (2 ** 31 - 1, 2 ** 31 - 1),
    # Unsigned integers.
    (uint(0), uint(0)),
    (uint(10), uint(10)),
    (uint(2 ** 32 - 1), uint(2 ** 32 - 1)),
    # Text.
    ("", ""),
    ("foo", "foo"),
    ("如此这般", "如此这般"),
    # Binary.
    (b"", b""),
    (b"foo", b"foo\x00"),
    # U8 array.
    (array("B", []), array("B", [])),
    (array("B", [0]), array("B", [0, 0, 0, 0])),
    (array("B", [10]), array("B", [10, 0, 0, 0])),
    (array("B", [2 ** 8 - 1]), array("B", [2 ** 8 - 1, 0, 0, 0])),
    # U16 array.
    (array("H", []), array("H", [])),
    (array("H", [0]), array("H", [0, 0])),
    (array("H", [10]), array("H", [10, 0])),
    (array("H", [2 ** 16 - 1]), array("H", [2 ** 16 - 1, 0])),
    # U32 array.
    (array("I", []), array("I", [])),
    (array("I", [0]), array("I", [0])),
    (array("I", [10]), array("I", [10])),
    (array("I", [2 ** 32 - 1]), array("I", [2 ** 32 - 1])),
    # I8 array.
    (array("b", []), array("b", [])),
    (array("b", [-2 ** 7]), array("b", [-2 ** 7, 0, 0, 0])),
    (array("b", [0]), array("b", [0, 0, 0, 0])),
    (array("b", [10]), array("b", [10, 0, 0, 0])),
    (array("b", [2 ** 7 - 1]), array("b", [2 ** 7 - 1, 0, 0, 0])),
    # I16 array.
    (array("h", []), array("h", [])),
    (array("h", [-2 ** 15]), array("h", [-2 ** 15, 0])),
    (array("h", [0]), array("h", [0, 0])),
    (array("h", [10]), array("h", [10, 0])),
    (array("h", [2 ** 15 - 1]), array("h", [2 ** 15 - 1, 0])),
    # I32 array.
    (array("i", []), array("i", [])),
    (array("i", [-2 ** 31]), array("i", [-2 ** 31])),
    (array("i", [0]), array("i", [0])),
    (array("i", [10]), array("i", [10])),
    (array("i", [2 ** 31 - 1]), array("i", [2 ** 31 - 1])),
]


class PacketDatasTestCase(unittest.TestCase):

    def testDecodeRealPacketData(self):
        self.assertEqual(decode_packet(REAL_PACKET).fields, [
            FieldData(name="HELO", id=0, params={
                "NCPV": "Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__",
                "SEID": "monitor",
                "MACA": "00:24:81:b4:49:34",
            }),
        ])

    def testEncodeDecodeValue(self):
        packet_timestamp = datetime.now(tz=timezone.utc)
        for value, expected_value in PACKET_VALUES:
            with self.subTest(value=value, expected_value=expected_value):
                expected_packet = PacketData("PACK", 10, packet_timestamp, b"INFO", [
                    FieldData("FIEL", 20, {"PARA": expected_value}),
                ])
                decoded_packet = decode_packet(encode_packet("PACK", 10, packet_timestamp, b"INFO", [
                    FieldData("FIEL", 20, {"PARA": value}),
                ]))
                self.assertEqual(decoded_packet, expected_packet)
