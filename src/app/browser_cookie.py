from __future__ import annotations

from starlette.requests import HTTPConnection


def browser_cookie(connection: HTTPConnection, name: str) -> str:
    headers = connection.headers.getlist("cookie")

    if sum(map(len, headers)) > 8192:
        return ""

    values = [
        part.partition("=")[2].strip()
        for header in headers
        for part in header.split(";")
        if part.partition("=")[0].strip() == name
    ]
    return values[0] if len(values) == 1 else ""
