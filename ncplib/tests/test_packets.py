import unittest
from hypothesis import given, strategies as st
from ncplib.packets import decode_packet, encode_packet, Packet, Field
from ncplib.tests.strategies import timestamps, uints, names, fields


TEST_PACKET = (
    b"\xdd\xcc\xbb\xaaLINK'\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00s\xe9\x8eT(\x05\x1b&4I\xb4\x81HELO\x1d"
    b"\x00\x00\x00\x00\x00\x00\x00NCPV\x0f\x00\x00\x02Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__\x00SEID"
    b"\x04\x00\x00\x02monitor\x00MACA\x07\x00\x00\x0200:24:81:b4:49:34\x00\x00\x00\x00\x00\x00\x00\xaa\xbb\xcc\xdd"
)


class PacketsTestCase(unittest.TestCase):

    def testDecodeKnownPacket(self):
        self.assertEqual(decode_packet(TEST_PACKET).fields, [
            Field(name="HELO", id=0, params={
                "NCPV": "Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__",
                "SEID": "monitor",
                "MACA": "00:24:81:b4:49:34",
            }),
        ])

    @given(names(), uints(32), timestamps(), st.binary(min_size=4, max_size=4), st.lists(fields()))
    def testEncodeInvertsDecode(self, packet_type, packet_id, timestamp, info, fields):
        expected_packet = Packet(packet_type, packet_id, timestamp, info, fields)
        self.assertEqual(decode_packet(encode_packet(packet_type, packet_id, timestamp, info, fields)), expected_packet)
