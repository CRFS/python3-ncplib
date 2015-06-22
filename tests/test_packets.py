import string
from array import array
from functools import partial

from hypothesis import given
import hypothesis.strategies as st
from hypothesis.extra.datetime import datetimes

from ncplib.packets import decode_packet, encode_packet, Packet, Field
from ncplib.values import uint


# Testing of known values.

TEST_PACKET = b"\xdd\xcc\xbb\xaaLINK'\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00s\xe9\x8eT(\x05\x1b&4I\xb4\x81HELO\x1d\x00\x00\x00\x00\x00\x00\x00NCPV\x0f\x00\x00\x02Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__\x00SEID\x04\x00\x00\x02monitor\x00MACA\x07\x00\x00\x0200:24:81:b4:49:34\x00\x00\x00\x00\x00\x00\x00\xaa\xbb\xcc\xdd"

def test_decode_known_packet():
    assert decode_packet(TEST_PACKET).fields == [
        Field(name="HELO", id=0, params={
            "NCPV": "Beta B01.025:Nov  7 2012, 11:27:52 __TESTING_ONLY__",
            "SEID": "monitor",
            "MACA": "00:24:81:b4:49:34",
        }),
    ]


# Hypothesis helpers.

def signed(size):
    return st.integers(
        min_value = -2 ** (size - 1),
        max_value = 2 ** (size - 1) - 1,
    )

def unsigned(size):
    return st.integers(
        min_value = 0,
        max_value = 2 ** size - 1,
    )

NAME = st.text(
    alphabet = string.ascii_uppercase,
    min_size = 3,
    max_size = 4,
)

def with_padding(resolution, pad_value):
    def do_with_padding(value):
        return value + pad_value * (-len(value) % resolution)
    return do_with_padding

FIELD = st.builds(Field,
    name = NAME,
    id = unsigned(32),
    params = st.dictionaries(
        keys = NAME,
        values = st.one_of(
            signed(32),
            st.builds(uint, unsigned(32)),
            st.text().map(lambda v: v.replace("\x00", "")),
            st.binary().map(with_padding(4, b"\x00")),
            st.builds(partial(array, "B"), st.lists(unsigned(8)).map(with_padding(4, [0]))),
            st.builds(partial(array, "H"), st.lists(unsigned(16)).map(with_padding(2, [0]))),
            st.builds(partial(array, "I"), st.lists(unsigned(32))),
            st.builds(partial(array, "b"), st.lists(signed(8)).map(with_padding(4, [0]))),
            st.builds(partial(array, "h"), st.lists(signed(16)).map(with_padding(2, [0]))),
            st.builds(partial(array, "i"), st.lists(signed(32))),
        ),
    ),
)


# Firehose-style encoding tests.

@given(
    packet_type = NAME,
    packet_id = unsigned(32),
    timestamp = datetimes(min_year=1970, max_year=2100),
    info = st.binary(min_size=4, max_size=4),
    fields = st.lists(FIELD),
)
def test_encode_inverts_decode(packet_type, packet_id, timestamp, info, fields):
    assert decode_packet(encode_packet(packet_type, packet_id, timestamp, info, fields)) == Packet(packet_type, packet_id, timestamp, info, fields)
