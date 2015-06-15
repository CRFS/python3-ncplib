from unittest import TestCase

from ncplib.encoding import decode_packet, encode_packet, Field


TEST_PACKET = b"\xdd\xcc\xbb\xaaLINK'\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00s\xe9\x8eT(\x05\x1b&4I\xb4\x81HELO\x1d\x00\x00\x00\x00\x00\x00\x00NCPV\x0f\x00\x00\x02Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__\x00SEID\x04\x00\x00\x02monitor\x00MACA\x07\x00\x00\x0200:24:81:b4:49:34\x00\x00\x00\x00\x00\x00\x00\xaa\xbb\xcc\xdd"


class DecoderTestCase(TestCase):

    maxDiff = None

    def testDecodePacketFields(self):
        self.assertEqual(decode_packet(TEST_PACKET).fields, [
            Field(name=b"HELO", id=0, params={
                b"NCPV": "Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__",
                b"SEID": "monitor",
                b"MACA": "00:24:81:b4:49:34",
            }),
        ])


class EncoderTestCase(TestCase):

    def testEncodePacket(self):
        packet = decode_packet(TEST_PACKET)
        encoded_packet = encode_packet(*packet)
        self.assertEqual(encoded_packet, TEST_PACKET)
