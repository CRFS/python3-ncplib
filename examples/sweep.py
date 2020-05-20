"""
NCP sweep data example.

Connects to a node and requests a single sweep to be performed. Prints the result to stdout.
"""
import asyncio
import ncplib


# The node to connect to. Can be a DNS name or an IP address.
NODE_HOST = "127.0.0.1"


async def main():
    """
    The async main method.

    Connects to a node and requests a single sweep to be performed. Prints the result to stdout.
    """
    # Connect to the node.
    async with await ncplib.connect(NODE_HOST) as connection:
        # Send a single DSPC command to the node.
        response = connection.send("DSPC", "SWEP", FSTA=10000, FSTP=18000, INPT=1, BDEX=1, BINP=2)
        # Wait for the node to reply.
        field = await response.recv()
        print(field)


# Run the async main method if this file is run as a script.
if __name__ == "__main__":
    asyncio.run(main())
