import asyncio
import pytest
from functools import wraps
from hypothesis import given
from ncplib import connect, start_server
from tests.conftest import names, params


# Helpers.

async def echo_handler(connection):
    async for params in connection.recv_iter():
        params.send(**params)


def wait_for(event_loop, coroutine):
    return event_loop.run_until_complete(asyncio.wait_for(coroutine, timeout=1, loop=event_loop))


def async_test(client_connected):
    def decorator(func):
        @wraps(func)
        def do_async_test(event_loop, client, *args, **kwargs):
            wait_for(event_loop, func(client, *args, **kwargs))
        return do_async_test
    return decorator


# Fixtures.


@pytest.yield_fixture
def server(event_loop, unused_tcp_port):
    server = wait_for(event_loop, start_server(
        echo_handler,
        "127.0.0.1",
        unused_tcp_port,
        loop=event_loop,
    ))
    try:
        yield server
    finally:
        server.close()
        wait_for(event_loop, server.wait_closed())


@pytest.yield_fixture
def client(event_loop, unused_tcp_port, server):
    client = wait_for(event_loop, connect(
        "127.0.0.1",
        unused_tcp_port,
        loop=event_loop,
    ))
    try:
        yield client
    finally:
        client.close()
        wait_for(event_loop, client.wait_closed())


# Client tests.

@given(
    packet_type=names(),
    field_name=names(),
    params=params(),
)
@async_test(echo_handler)
async def test_execute(client, packet_type, field_name, params):
    response_params = await client.execute(packet_type, field_name, **params)
    assert response_params == params
