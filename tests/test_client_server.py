import pytest
from ncplib import connect, start_server


@pytest.yield_fixture
def client_server(unused_tcp_port):
    pass
