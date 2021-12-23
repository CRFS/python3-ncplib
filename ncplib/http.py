import asyncio
from http.client import parse_headers, HTTPMessage, HTTPException
from io import BytesIO
import re
from typing import Tuple
from ncplib.errors import DecodeError


RE_HTTP_STATUS = re.compile(r'^HTTP/1.1 (\d+) (.*?)$')
RE_HTTP_REQUEST = re.compile(r'^(.*?) (.*?) HTTP/1.1$')


async def decode_http_head(
    pattern: "re.Pattern[str]",
    reader: asyncio.StreamReader,
) -> Tuple[Tuple[str, ...], HTTPMessage]:
    try:
        line_bytes, headers_bytes = (await reader.readuntil(b"\r\n\r\n")).split(b"\r\n", 1)
    except asyncio.IncompleteReadError as ex:  # pragma: no cover
        raise DecodeError(f"Invalid HTTP tunnel response: {ex.partial.decode('latin1')}")
    # Decode head.
    line = line_bytes.decode("latin1")
    match = pattern.match(line)
    if match is None:  # pragma: no cover
        raise DecodeError(f"Invalid HTTP tunnel response: {line}")
    # Decode headers.
    try:
        headers = parse_headers(BytesIO(headers_bytes))
    except HTTPException as ex:  # pragma: no cover
        raise DecodeError(ex) from ex
    # All done!
    return match.groups(), headers
