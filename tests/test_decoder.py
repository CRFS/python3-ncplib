import asyncio
from unittest import TestCase

from ncplib.decoder import decode_packet
from ncplib.concurrent import sync


TEST_PACKET_ENCODED = b"\xdd\xcc\xbb\xaaLINK'\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00s\xe9\x8eT(\x05\x1b&4I\xb4\x81HELO\x1d\x00\x00\x00\x00\x00\x00\x00NCPV\x0f\x00\x00\x02Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__\x00SEID\x04\x00\x00\x02monitor\x00MACA\x07\x00\x00\x0200:24:81:b4:49:34\x00\x00\x00\x00\x00\x00\x00\xaa\xbb\xcc\xdd"

TEST_PACKET_DECODED = {
    "HELO": {
        "NCPV": "Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__",
        "SEID": "monitor",
        "MACA": "00:24:81:b4:49:34",
    },
}


decode_packet = sync()(decode_packet)


class DecoderTestCase(TestCase):

    def testDecodePacket(self):
        reader = asyncio.StreamReader()
        # Feed in two packets.
        reader.feed_data(TEST_PACKET_ENCODED)
        reader.feed_data(TEST_PACKET_ENCODED)
        reader.feed_eof()
        # Decode two packets.
        self.assertEqual(decode_packet(reader).fields, TEST_PACKET_DECODED)
        self.assertEqual(decode_packet(reader).fields, TEST_PACKET_DECODED)

