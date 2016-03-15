import asyncio
from datetime import datetime
import pytest
from hypothesis import given
from hypothesis.strategies import dictionaries
from hypothesis.internal.reflection import impersonate  # functools.wraps does not work with pytest fixtures.
from ncplib import Client, Server, CommandError, CommandWarning
from conftest import names, params, ints, text_no_nulls


# Helpers.

def async_test(client_connected):
    def decorator(func):
        @impersonate(func)
        def do_async_test(event_loop, unused_tcp_port, *args, **kwargs):
            async def async_test_runner():
                async with Server(client_connected, "127.0.0.1", unused_tcp_port, loop=event_loop):
                    async with Client("127.0.0.1", unused_tcp_port, loop=event_loop) as client:
                        await func(client, *args, **kwargs)
            event_loop.run_until_complete(asyncio.wait_for(async_test_runner(), timeout=1, loop=event_loop))
        return do_async_test
    return decorator


async def echo_handler(connection):
    async for message in connection:
        message.send(**message)


async def assert_messages(response, packet_type, expected_messages):
    messages = {}
    while len(messages) < len(expected_messages):
        message = await response.recv()
        messages[message.field_name] = message
        # Check the message structure.
        assert message.packet_type == packet_type
        assert isinstance(message.packet_timestamp, datetime)
        assert message.field_name in expected_messages
        assert isinstance(message.field_id, int)
        assert len(message) == len(expected_messages[message.field_name])
    # Check the message content.
    assert messages == expected_messages


# Tests.

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


@given(
    packet_type=names(),
    field_name=names(),
    params=params(),
)
@async_test(echo_handler)
async def test_send(client, packet_type, field_name, params):
    response = client.send(packet_type, field_name, **params)
    await assert_messages(response, packet_type, {field_name: params})


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
    await assert_messages(response, packet_type, {field_name: params})


@given(
    packet_type=names(),
    fields=dictionaries(names(), params())
)
@async_test(echo_handler)
async def test_send_packet(client, packet_type, fields):
    response = client.send_packet(packet_type, **fields)
    await assert_messages(response, packet_type, fields)


@given(
    packet_type=names(),
    fields=dictionaries(names(), params())
)
@async_test(echo_handler)
async def test_send_packet_deprecated_api(client, packet_type, fields):
    with pytest.warns(DeprecationWarning):
        response = client.send(packet_type, fields)
    await assert_messages(response, packet_type, fields)


@given(
    packet_type=names(),
    field_name=names(),
    params=params(),
    junk_field_name=names(),
)
@async_test(echo_handler)
async def test_recv_field_connection_filters_messages(client, packet_type, field_name, params, junk_field_name):
    client.send(packet_type, junk_field_name, **params)
    client.send(packet_type, field_name, **params)
    message = await client.recv_field(packet_type, field_name)
    assert message == params


@given(
    packet_type=names(),
    field_name=names(),
    params=params(),
    junk_params=params(),
)
@async_test(echo_handler)
async def test_recv_field_response_filters_messages(client, packet_type, field_name, params, junk_params):
    client.send(packet_type, field_name, **junk_params)
    response = client.send(packet_type, field_name, **params)
    message = await response.recv_field(field_name)
    assert message == params


async def server_error_handler(connection):
    await connection.recv()
    raise Exception("Boom")


@async_test(server_error_handler)
async def test_server_error(client):
    client.send("BOOM", "BOOM")
    with pytest.raises(CommandError) as exc_info:
        await client.recv()
    exception = exc_info.value
    assert exception.message.packet_type == "LINK"
    assert exception.message.field_name == "ERRO"
    assert exception.detail == "Server error"
    assert exception.code == 500


@given(
    packet_type=names(),
    field_name=names().filter(lambda v: v != "ERRO"),
    detail=text_no_nulls(),
    code=ints(),
)
@async_test(echo_handler)
async def test_error(client, packet_type, field_name, detail, code):
    client.send(packet_type, field_name, ERRO=detail, ERRC=code)
    with pytest.raises(CommandError) as exc_info:
        await client.recv()
    exception = exc_info.value
    assert exception.message.packet_type == packet_type
    assert exception.message.field_name == field_name
    assert exception.detail == detail
    assert exception.code == code


@given(
    packet_type=names(),
    field_name=names().filter(lambda v: v != "WARN"),
    detail=text_no_nulls(),
    code=ints(),
)
@async_test(echo_handler)
async def test_warning(client, packet_type, field_name, detail, code):
    client.send(packet_type, field_name, WARN=detail, WARC=code)
    with pytest.warns(CommandWarning) as warnings:
        await client.recv()
    assert len(warnings) == 1
    warning = warnings[0].message
    assert warning.message.packet_type == packet_type
    assert warning.message.field_name == field_name
    assert warning.detail == detail
    assert warning.code == code
