import array
from datetime import datetime, timezone
import timeit
from ncplib.packets import encode_packet, decode_packet
from ncplib import uint


PACKET = ("TEST", 1, datetime.now(tz=timezone.utc), b"INFO", [
    ("FIEL", 2, [
        ("INT", -99),
        ("UINT", uint(99)),
        ("STR", "foo!"),
        ("BYTE", b"bar!"),
        ("ARR", array.array("i", [10])),
    ]),
])


def benchmark():
    decoded = decode_packet(encode_packet(*PACKET))
    assert decoded == PACKET, "{} != {}".format(decoded, PACKET)


def main():
    print("Starting packet encoding benchmark...")
    result = min(timeit.repeat(benchmark, number=50000))
    print("Result: {}".format(result))


if __name__ == "__main__":
    main()
