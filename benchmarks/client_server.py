import asyncio
from functools import partial
import timeit
import ncplib


DATA = b"fooobaar" * 1024


class EchoApplication(ncplib.Application):

    @asyncio.coroutine
    def handle_field_LINK_ECHO(self, field):
        field.send(DATA=field["DATA"])


def benchmark(loop, client):
    response = client.send("LINK", "ECHO", DATA=DATA)
    assert loop.run_until_complete(response.recv())["DATA"] == DATA


def main():
    # Set up the fixture.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server = loop.run_until_complete(ncplib.start_server(EchoApplication, "127.0.0.1", 0))
    client = loop.run_until_complete(ncplib.connect("127.0.0.1", server.sockets[0].getsockname()[1]))
    # Run the benchmark.
    try:
        print("Starting client server benchmark...")
        result = min(timeit.repeat(partial(benchmark, loop, client), number=500))
        print("Result: {}".format(result))
    finally:
        client.close()
        server.close()
        loop.run_until_complete(server.wait_closed())
        # Shut down the fixture.
        loop.close()
        asyncio.set_event_loop(None)


if __name__ == "__main__":
    main()
