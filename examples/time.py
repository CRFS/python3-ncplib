"""
NCP time data example.

Connects to a node and requests a single time capture to be performed. Prints the result to stdout.
"""
import asyncio
import ncplib


# The node to connect to. Can be a DNS name or an IP address.
NODE_HOST = "127.0.0.1"

# Frequency.
FREQ_HZ = 2400.12e6  # 2400.12 MHz

# Realtime bandwidth.
RTBW_HZ = 10e6  # 10 MHz

# Capture length.
DURATION_S = 1e-3  # 1 ms.


def split_milli(value):
    n = int(value * 1e3)
    return (n // 1000000000, n % 1000000000)


def split_nano(value):
    n = int(value * 1e9)
    return (n // 1000000000, n % 1000000000)


async def main():
    """
    The async main method.

    Connects to a node and requests a single time capture to be performed. Prints the result to stdout.
    """
    # Connect to the node.
    async with await ncplib.connect(NODE_HOST) as connection:
        # Send a single DSPC command to the node.
        fctr, fctm = split_milli(FREQ_HZ)
        rbme, rbmi = split_milli(RTBW_HZ)
        lsec, lnan = split_nano(DURATION_S)
        response = connection.send("DSPC", "TIME", FCTR=fctr, FCTM=fctm, RBME=rbme, RBMI=rbmi, LSEC=lsec, LNAN=lnan)
        # Wait for the node to reply.
        field = await response.recv()
        print(field)


# Run the async main method if this file is run as a script.
if __name__ == "__main__":
    asyncio.run(main())
