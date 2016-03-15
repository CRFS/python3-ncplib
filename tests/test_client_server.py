import asyncio
import pytest
from hypothesis import given
from hypothesis.strategies import dictionaries
from hypothesis.internal.reflection import impersonate  # functools.wraps does not work with pytest fixtures.
from ncplib import connect, start_server, CommandError
from conftest import names, params


# Helpers.

def wait_for(event_loop, coroutine):
    return event_loop.run_until_complete(asyncio.wait_for(coroutine, timeout=1, loop=event_loop))


def async_test(client_connected):
    def decorator(func):
        @impersonate(func)
        def do_async_test(event_loop, unused_tcp_port, *args, **kwargs):
            server = wait_for(event_loop, start_server(
                client_connected,
                "127.0.0.1",
                unused_tcp_port,
                loop=event_loop,
            ))
            try:
                client = wait_for(event_loop, connect(
                    "127.0.0.1",
                    unused_tcp_port,
                    loop=event_loop,
                ))
                try:
                    wait_for(event_loop, func(client, *args, **kwargs))
                finally:
                    client.close()
                    wait_for(event_loop, client.wait_closed())
            finally:
                server.close()
                wait_for(event_loop, server.wait_closed())
        return do_async_test
    return decorator


async def echo_handler(connection):
    async for message in connection:
        message.send(**message)


async def assert_messages(response, expected_messages):
    messages = {}
    while len(messages) != len(expected_messages):
        message = await response.recv()
        messages[message.field.name] = message
    assert messages == expected_messages


# Execute tests.

@given(
    packet_type=names(),
    field_name=names(),
    params=params(),
)
@async_test(echo_handler)
async def test_execute(client, packet_type, field_name, params):
    message = await client.execute(packet_type, field_name, **params)
    assert message == params


@given(
    packet_type=names(),
    field_name=names(),
    params=params(),
)
@async_test(echo_handler)
async def test_execute_deprecated_api(client, packet_type, field_name, params):
    with pytest.warns(DeprecationWarning):
        message = await client.execute(packet_type, field_name, params)
    assert message == params


# Send tests.

@given(
    packet_type=names(),
    field_name=names(),
    params=params(),
)
@async_test(echo_handler)
async def test_send(client, packet_type, field_name, params):
    response = client.send(packet_type, field_name, **params)
    await assert_messages(response, {field_name: params})


@given(
    packet_type=names(),
    field_name=names(),
    params=params(),
    junk_params=params(),
)
@async_test(echo_handler)
async def test_send_filters_messages(client, packet_type, field_name, params, junk_params):
    # Send some junk.
    client.send(packet_type, field_name, **junk_params)
    # Send a message.
    response = client.send(packet_type, field_name, **params)
    await assert_messages(response, {field_name: params})


# Send many tests.

@given(
    packet_type=names(),
    fields=dictionaries(names(), params())
)
@async_test(echo_handler)
async def test_send_packet(client, packet_type, fields):
    response = client.send(packet_type, fields)
    await assert_messages(response, fields)


@given(
    packet_type=names(),
    fields=dictionaries(names(), params())
)
@async_test(echo_handler)
async def test_send_packet_deprecated_api(client, packet_type, fields):
    with pytest.warns(DeprecationWarning):
        response = client.send(packet_type, fields)
    await assert_messages(response, fields)


# Server error tests.

async def server_error_handler(connection):
    await connection.recv()
    raise Exception("Boom!")


@async_test(server_error_handler)
async def test_server_error(client):
    with pytest.raises(CommandError) as exc_info:
        client.send("BOOM", "BOOM")
        await client.recv()
    assert exc_info.value.message.packet.type == "LINK"
    assert exc_info.value.message.field.name == "ERRO"
    assert exc_info.value.detail == "Server error"
    assert exc_info.value.code == 500
