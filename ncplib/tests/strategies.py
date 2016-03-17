import string
from array import array
from datetime import datetime, timezone
from functools import partial
from hypothesis import strategies as st
from hypothesis.extra.datetime import datetimes
from ncplib.packets import Field
from ncplib.values import uint


def ints(size=32):
    return st.integers(
        min_value=-2 ** (size - 1),
        max_value=2 ** (size - 1) - 1,
    )


def uints(size=32):
    return st.integers(
        min_value=0,
        max_value=2 ** size - 1,
    ).map(uint)


def names():
    return st.text(
        alphabet=string.ascii_uppercase,
        min_size=3,
        max_size=4,
    )


def _with_padding(resolution, pad_value):
    def do_with_padding(value):
        return value + pad_value * (-len(value) % resolution)
    return do_with_padding


def values():
    return st.one_of(
        ints(),
        uints(),
        st.text().map(lambda v: v.replace("\x00", "")),
        st.binary().map(_with_padding(4, b"\x00")),
        st.builds(partial(array, "B"), st.lists(uints(8)).map(_with_padding(4, [0]))),
        st.builds(partial(array, "H"), st.lists(uints(16)).map(_with_padding(2, [0]))),
        st.builds(partial(array, "I"), st.lists(uints(32))),
        st.builds(partial(array, "b"), st.lists(ints(8)).map(_with_padding(4, [0]))),
        st.builds(partial(array, "h"), st.lists(ints(16)).map(_with_padding(2, [0]))),
        st.builds(partial(array, "i"), st.lists(ints(32))),
    )


def params():
    return st.dictionaries(
        keys=names(),
        values=values(),
    )


def fields():
    return st.builds(
        Field,
        name=names(),
        id=uints(),
        params=params(),
    )


_UNIX_EPOCH = datetime(1970, 1, 1, 0, 0, tzinfo=timezone.utc)


def timestamps():
    return datetimes(min_year=1970, max_year=2100).filter(lambda v: v >= _UNIX_EPOCH)
