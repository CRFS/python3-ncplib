import asyncio, os, warnings
from array import array
from functools import wraps

import pytest

from ncplib.client import connect
from ncplib.errors import CommandWarning


NCPLIB_TEST_CLIENT_HOST = os.environ.get("NCPLIB_TEST_CLIENT_HOST")
NCPLIB_TEST_CLIENT_PORT = os.environ.get("NCPLIB_TEST_CLIENT_PORT")

pytestmark = pytest.mark.skipif(
    not NCPLIB_TEST_CLIENT_HOST,
    not NCPLIB_TEST_CLIENT_PORT,
    reason = "NCPLIB_TEST_CLIENT_HOST and NCPLIB_TEST_CLIENT_PORT not set in environ",
)


# Fixtures.

@pytest.yield_fixture
def client(event_loop):
    # Set up debug warnings.
    with warnings.catch_warnings():
        warnings.simplefilter("default", ResourceWarning)
        warnings.simplefilter("ignore", CommandWarning)
        # Use asyncio debug.
        event_loop.set_debug(True)
        # Connect the client.
        client = event_loop.run_until_complete(asyncio.wait_for(connect(NCPLIB_TEST_CLIENT_HOST, NCPLIB_TEST_CLIENT_PORT, loop=event_loop), loop=event_loop, timeout=30))
        try:
            yield client
        finally:
            client.close()
            event_loop.run_until_complete(asyncio.wait_for(client.wait_closed(), loop=event_loop, timeout=30))


# Test helpers.

def require_loop(func):
    @wraps(func)
    def do_require_loop(self):
        # Set up debug warnings.
        
            # Set up a debug loop.
            loop = asyncio.new_event_loop()
            try:
                loop.set_debug(True)
                loop.run_until_complete(asyncio.wait_for(func(self, loop), loop=loop, timeout=30))
            finally:
                loop.close()
    return do_require_loop

def require_client(func):
    @wraps(func)
    @asyncio.coroutine
    def do_require_client(self, loop):
        # Connect the client.
        
        try:
            yield from func(self, loop, client)
        finally:
            client.close()
            yield from client.wait_closed()
    return do_require_client


# Test assertions.

def assert_stat_params(params):
    assert isinstance(params["OCON"], int)
    assert isinstance(params["CADD"], str)
    assert isinstance(params["CIDS"], str)
    assert isinstance(params["RGPS"], str)
    assert isinstance(params["ELOC"], int)

def assert_swep_params(params):
    assert isinstance(params["PDAT"], array)
    assert params["PDAT"].typecode == "B"

def assert_time_params(params):
    assert params["SAMP"] == 1024
    assert params["FCTR"] == 1200
    assert isinstance(params["DIQT"], array)
    assert params["DIQT"].typecode == "h"
    assert len(params["DIQT"]) == 2048
    

# Simple integration tests.

@pytest.mark.asyncio
def testStat(client):
    params = yield from client.execute("NODE", "STAT")
    assert_stat_params(params)


# Testing the read machinery.

@pytest.mark.asyncio
def testStatRecvField(client):
    params = yield from client.send("NODE", {"STAT": {}}).recv_field("STAT")
    assert_stat_params(params)


# More complex commands with an ACK.

@pytest.mark.asyncio
def testDspcSwep(client):
    params = yield from client.execute("DSPC", "SWEP")
    assert_swep_params(params)

@pytest.mark.asyncio
def testDspcTime(client):
    params = yield from client.execute("DSPC", "TIME", {"SAMP": 1024, "FCTR": 1200})
    assert_time_params(params)


# Combination commands.

@pytest.mark.asyncio
def testMultiCommands(event_loop, client):
    response = client.send("DSPC", {"SWEP": {}, "TIME": {"SAMP": 1024, "FCTR": 1200}})
    swep_params, time_params = yield from asyncio.gather(response.recv_field("SWEP"), response.recv_field("TIME"), loop=event_loop)
    assert_swep_params(swep_params)
    assert_time_params(time_params)


# Loop tests.

@pytest.mark.asyncio
def testDsplSwep(client):
    response = client.send("DSPL", {"SWEP": {}})
    params = yield from response.recv_field("SWEP")
    assert_swep_params(params)
    params = yield from response.recv_field("SWEP")
    assert_swep_params(params)

@pytest.mark.asyncio
def testDsplTime(client):
    response = client.send("DSPL", {"TIME": {"SAMP": 1024, "FCTR": 1200}})
    params = yield from response.recv_field("TIME")
    assert_time_params(params)
    params = yield from response.recv_field("TIME")
    assert_time_params(params)
