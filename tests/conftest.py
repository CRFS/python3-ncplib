import os
import string
from array import array
from datetime import datetime, timezone
from functools import partial
from hypothesis import settings
from hypothesis.strategies import integers, text, builds, dictionaries, one_of, binary, lists
from hypothesis.extra.datetime import datetimes
from ncplib.packets import Field
from ncplib.values import uint


settings.register_profile("ci", settings())
settings.register_profile("dev", settings(timeout=0.5, min_satisfying_examples=1))
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))


# Strategies.

def ints(size=32):
    return integers(
        min_value=-2 ** (size - 1),
        max_value=2 ** (size - 1) - 1,
    )


def uints(size=32):
    return integers(
        min_value=0,
        max_value=2 ** size - 1,
    ).map(uint)


def names():
    return text(
        alphabet=string.ascii_uppercase,
        min_size=3,
        max_size=4,
    )


def with_padding(resolution, pad_value):
    def do_with_padding(value):
        return value + pad_value * (-len(value) % resolution)
    return do_with_padding


def text_no_nulls():
    return text().map(lambda v: v.replace("\x00", ""))


def params():
    return dictionaries(
        keys=names(),
        values=one_of(
            ints(),
            uints(),
            text_no_nulls(),
            binary().map(with_padding(4, b"\x00")),
            builds(partial(array, "B"), lists(uints(8)).map(with_padding(4, [0]))),
            builds(partial(array, "H"), lists(uints(16)).map(with_padding(2, [0]))),
            builds(partial(array, "I"), lists(uints(32))),
            builds(partial(array, "b"), lists(ints(8)).map(with_padding(4, [0]))),
            builds(partial(array, "h"), lists(ints(16)).map(with_padding(2, [0]))),
            builds(partial(array, "i"), lists(ints(32))),
        ),
    )


def fields():
    return builds(
        Field,
        name=names(),
        id=uints(),
        params=params(),
    )


UNIX_EPOCH = datetime(1970, 1, 1, 0, 0, tzinfo=timezone.utc)


def timestamps():
    return datetimes(min_year=1970, max_year=2100).filter(lambda v: v >= UNIX_EPOCH)
