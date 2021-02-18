from __future__ import annotations
import unittest
from array import array
from datetime import datetime, timezone
from math import inf
from typing import Sequence, Tuple
from ncplib.packets import Param, encode_packet, decode_packet
from ncplib import u32, i64, u64, f64


REAL_PACKET = (
    b"\xdd\xcc\xbb\xaaLINK'\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00s\xe9\x8eT(\x05\x1b&4I\xb4\x81HELO\x1d"
    b"\x00\x00\x00\x00\x00\x00\x00NCPV\x0f\x00\x00\x02Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__\x00"
    b"SEID\x04\x00\x00\x02monitor\x00MACA\x07\x00\x00\x0200:24:81:b4:49:34\x00\x00\x00\x00\x00\x00\x00\xaa\xbb"
    b"\xcc\xdd"
)


REAL_PACKET_EMBEDDED_FOOTER_BUG = (
    b'\xdd\xcc\xbb\xaaSTAT[\x00\x00\x00\n\x00\x00\x00\x01\x00\x00\x00\xb5_\xe4U\x10\xd9A\x0c\t\x07\x00\x89'
    b'STAT*\x00\x00\x00\x01\x00\x00\x00OCON\x03\x00\x00\x00\x03\x00\x00\x00CADD\x0b\x00\x00\x02127.0.0.1,'
    b'127.0.0.1,192.168.1.28\x00\x00\x00\x00CIDS\x0c\x00\x00\x02rfeye000709,rfeye000709,python3-ncplib\x00'
    b'IRGPS\x08\x00\x00\x02no GPS,no GPS,no GPS\x00"maELOC\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    b'\xaa\xbb\xcc\xddSGPS\'\x00\x00\x00\x01\x00\x00\x00LATI\x03\x00\x00\x00\x00\xf5\x0c\x03LONG\x03\x00'
    b'\x00\x00`y\xfe\xffSTAT\x03\x00\x00\x00\x01\x00\x00\x00GFIX\x03\x00\x00\x00\x01\x00\x00\x00SATS\x03'
    b'\x00\x00\x00\t\x00\x00\x00SPEE\x03\x00\x00\x00\x94O\x00\x00HEAD\x03\x00\x00\x00\xa0\x10\x00\x00ALTI'
    b'\x03\x00\x00\x00(#\x00\x00UTIM\x03\x00\x00\x00\xb4_\xe4UTSTR\t\x00\x00\x02Mon Aug 31 14:07:48 2015'
    b'\x00on"\x00\x00\x00\x00\xaa\xbb\xcc\xdd'
)


PACKET_VALUES: Sequence[Tuple[Param, Param]] = [
    # bool.
    (True, 1),
    (False, 0),
    # i32.
    (-2 ** 31, -2 ** 31),
    (0, 0),
    (10, 10),
    (2 ** 31 - 1, 2 ** 31 - 1),
    # u32.
    (u32(0), u32(0)),
    (u32(10), u32(10)),
    (u32(2 ** 32 - 1), u32(2 ** 32 - 1)),
    # i64.
    (i64(-2 ** 63), i64(-2 ** 63)),
    (i64(0), i64(0)),
    (i64(10), i64(10)),
    (i64(2 ** 63 - 1), i64(2 ** 63 - 1)),
    # u64.
    (u64(0), u64(0)),
    (u64(10), u64(10)),
    (u64(2 ** 64 - 1), u64(2 ** 64 - 1)),
    # f32.
    (-inf, -inf),
    (-1.0, -1.0),
    (0.0, 0.0),
    (1.0, 1.0),
    (inf, inf),
    # f64.
    (f64(-inf), f64(-inf)),
    (f64(-1.0), f64(-1.0)),
    (f64(0.0), f64(0.0)),
    (f64(1.0), f64(1.0)),
    (f64(inf), f64(inf)),
    # Text.
    ("", ""),
    ("foo", "foo"),
    ("如此这般", "如此这般"),
    # Binary.
    (b"", b""),
    (b"foo", b"foo\x00"),
    # u8 array.
    (array("B", []), array("B", [])),
    (array("B", [0]), array("B", [0, 0, 0, 0])),
    (array("B", [10]), array("B", [10, 0, 0, 0])),
    (array("B", [2 ** 8 - 1]), array("B", [2 ** 8 - 1, 0, 0, 0])),
    # u16 array.
    (array("H", []), array("H", [])),
    (array("H", [0]), array("H", [0, 0])),
    (array("H", [10]), array("H", [10, 0])),
    (array("H", [2 ** 16 - 1]), array("H", [2 ** 16 - 1, 0])),
    # u32 array.
    (array("I", []), array("I", [])),
    (array("I", [0]), array("I", [0])),
    (array("I", [10]), array("I", [10])),
    (array("I", [2 ** 32 - 1]), array("I", [2 ** 32 - 1])),
    # i8 array.
    (array("b", []), array("b", [])),
    (array("b", [-2 ** 7]), array("b", [-2 ** 7, 0, 0, 0])),
    (array("b", [0]), array("b", [0, 0, 0, 0])),
    (array("b", [10]), array("b", [10, 0, 0, 0])),
    (array("b", [2 ** 7 - 1]), array("b", [2 ** 7 - 1, 0, 0, 0])),
    # i16 array.
    (array("h", []), array("h", [])),
    (array("h", [-2 ** 15]), array("h", [-2 ** 15, 0])),
    (array("h", [0]), array("h", [0, 0])),
    (array("h", [10]), array("h", [10, 0])),
    (array("h", [2 ** 15 - 1]), array("h", [2 ** 15 - 1, 0])),
    # i32 array.
    (array("i", []), array("i", [])),
    (array("i", [-2 ** 31]), array("i", [-2 ** 31])),
    (array("i", [0]), array("i", [0])),
    (array("i", [10]), array("i", [10])),
    (array("i", [2 ** 31 - 1]), array("i", [2 ** 31 - 1])),
    # u64 array.
    (array("L", []), array("L", [])),
    (array("L", [0]), array("L", [0])),
    (array("L", [10]), array("L", [10])),
    (array("L", [2 ** 64 - 1]), array("L", [2 ** 64 - 1])),
    # i64 array.
    (array("l", []), array("l", [])),
    (array("l", [-2 ** 63]), array("l", [-2 ** 63])),
    (array("l", [0]), array("l", [0])),
    (array("l", [10]), array("l", [10])),
    (array("l", [2 ** 63 - 1]), array("l", [2 ** 63 - 1])),
    # f32 array.
    (array("f", [-inf, -1, 0, 1, inf]), array("f", [-inf, -1, 0, 1, inf])),
    # f64 array.
    (array("d", [-inf, -1, 0, 1, inf]), array("d", [-inf, -1, 0, 1, inf])),
]


class PacketDatasTestCase(unittest.TestCase):

    def testDecodeRealPacketData(self) -> None:
        self.assertEqual(decode_packet(REAL_PACKET)[4], [
            ("HELO", 0, [
                ("NCPV", "Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__"),
                ("SEID", "monitor"),
                ("MACA", "00:24:81:b4:49:34"),
            ]),
        ])

    def testEncodeDecodeValue(self) -> None:
        packet_timestamp = datetime.now(tz=timezone.utc)
        for value, expected_value in PACKET_VALUES:
            with self.subTest(type=value.__class__, value=value, expected_value=expected_value):
                expected_packet = ("PACK", 10, packet_timestamp, b"INFO", [
                    ("FIEL", 20, [("PARA", expected_value)]),
                ])
                decoded_packet = decode_packet(encode_packet("PACK", 10, packet_timestamp, b"INFO", [
                    ("FIEL", 20, [("PARA", value)]),
                ]))
                self.assertEqual(decoded_packet, expected_packet)
                decoded_value = decoded_packet[-1][0][-1][0][1]
                decoded_type = decoded_value.__class__
                self.assertIs(decoded_type, expected_value.__class__)
                if decoded_type is array:
                    self.assertEqual(value.typecode, decoded_value.typecode)  # type: ignore
