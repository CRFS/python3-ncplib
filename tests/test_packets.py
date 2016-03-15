from hypothesis import given
import hypothesis.strategies as st
from ncplib.packets import decode_packet, encode_packet, Packet, Field
from conftest import timestamps, uints, names, fields


# Testing of known values.

TEST_PACKET = (
    b"\xdd\xcc\xbb\xaaLINK'\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00s\xe9\x8eT(\x05\x1b&4I\xb4\x81HELO\x1d"
    b"\x00\x00\x00\x00\x00\x00\x00NCPV\x0f\x00\x00\x02Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__\x00SEID"
    b"\x04\x00\x00\x02monitor\x00MACA\x07\x00\x00\x0200:24:81:b4:49:34\x00\x00\x00\x00\x00\x00\x00\xaa\xbb\xcc\xdd"
)


def test_decode_known_packet():
    assert decode_packet(TEST_PACKET).fields == [
        Field(name="HELO", id=0, params={
            "NCPV": "Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__",
            "SEID": "monitor",
            "MACA": "00:24:81:b4:49:34",
        }),
    ]


# Encoding tests.

@given(
    packet_type=names(),
    packet_id=uints(32),
    timestamp=timestamps(),
    info=st.binary(min_size=4, max_size=4),
    fields=st.lists(fields()),
)
def test_encode_inverts_decode(packet_type, packet_id, timestamp, info, fields):
    expected_packet = Packet(packet_type, packet_id, timestamp, info, fields)
    assert decode_packet(encode_packet(packet_type, packet_id, timestamp, info, fields)) == expected_packet
