import asyncio
import re
from typing import Dict, Tuple
from ncplib.errors import DecodeError


RE_HTTP_STATUS = re.compile(r'^HTTP/1.1 (\d+) (.*?)$')
RE_HTTP_REQUEST = re.compile(r'^(.*?) (.*?) HTTP/1.1$')
_RE_HTTP_HEADER = re.compile(r'^(.*?): (.*?)$')


def _decode_http_line(pattern: re.Pattern[str], line: str) -> Tuple[str, ...]:
    match = pattern.match(line)
    if match is None:
        raise DecodeError(f"Invalid HTTP tunnel response: {line}")
    return match.groups()


async def decode_http_head(
    pattern: re.Pattern[str],
    reader: asyncio.StreamReader,
) -> Tuple[Tuple[str, ...], Dict[str, str]]:
    try:
        head = (await reader.readuntil(b"\r\n\r\n")).decode("latin1").split("\r\n")
    except asyncio.IncompleteReadError as ex:
        raise DecodeError(f"Invalid HTTP tunnel response: {ex.partial.decode('latin1')}")
    headers = {}
    for line in head[1:-2]:
        header_name, header_value = _decode_http_line(_RE_HTTP_HEADER, line)
        headers[header_name.lower()] = header_value
    return _decode_http_line(pattern, head[0]), headers
