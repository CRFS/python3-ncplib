import asyncio
import re
from typing import Dict, Tuple
from ncplib.connection import _wait_for
from ncplib.errors import DecodeError


RE_HTTP_STATUS = re.compile(r'^HTTP/1.1 (\d+) (.*?)\r\n$')
RE_HTTP_HEADER = re.compile(r'^(.*?): (.*?)\r\n$')


def decode_http_line(pattern: re.Pattern[str], line: bytes) -> Tuple[str, ...]:
    line_str = line.decode("latin1")
    match = pattern.match(line_str)
    if match is None:
        raise DecodeError(f"Invalid HTTP tunnel response: {line_str}")
    return match.groups()


async def decode_http_headers(reader: asyncio.StreamReader, timeout: int) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    while True:
        line = (await _wait_for(reader.readline(), timeout))
        if line == b"\r\n":
            return headers
        header_name, header_value = decode_http_line(RE_HTTP_HEADER, line)
        headers[header_name.lower()] = header_value
