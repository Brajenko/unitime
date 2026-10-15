from __future__ import annotations

import ipaddress
import socket
from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx

from app.adapters import BusyOccurrence
from app.adapters.ical import occurrences_from_ics


class LinkError(Exception):
    pass


def normalize_url(raw: str) -> str:
    url = raw.strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://") :]
    return url


def check_url(url: str) -> None:
    """Защита от SSRF: только http(s) и только публичные адреса."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise LinkError("Ссылка должна начинаться с http://, https:// или webcal://")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as error:
        raise LinkError("Не удалось найти сервер по этой ссылке") from error
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise LinkError("Ссылка ведёт на внутренний адрес")


def download(url: str) -> str:
    current = normalize_url(url)
    with httpx.Client(timeout=Constants.TIMEOUT_SECONDS, follow_redirects=False) as client:
        for _ in range(Constants.MAX_REDIRECTS + 1):
            check_url(current)
            with client.stream("GET", current, headers={"User-Agent": Constants.USER_AGENT}) as response:
                if response.is_redirect and response.headers.get("location"):
                    current = urljoin(current, response.headers["location"])
                    continue
                if response.status_code >= 400:
                    raise LinkError(f"Сервер ответил {response.status_code}. Нужна публичная ссылка на календарь.")
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > Constants.MAX_BYTES:
                        raise LinkError("Файл календаря слишком большой")
                    chunks.append(chunk)
                return b"".join(chunks).decode("utf-8", errors="replace")
    raise LinkError("Слишком много перенаправлений")


def title_for(url: str) -> str:
    host = urlparse(normalize_url(url)).hostname or "календарь"
    return f"Календарь по ссылке ({host})"


def validate(url: str) -> None:
    payload = download(url)
    if "BEGIN:VCALENDAR" not in payload:
        raise LinkError("По ссылке нет календаря в формате iCalendar (.ics)")


def fetch_busy(secret: dict, _external_id: str, window_start: datetime, window_end: datetime) -> list[BusyOccurrence]:
    return occurrences_from_ics(download(secret["url"]), window_start, window_end)


class Constants:
    TIMEOUT_SECONDS = 10.0
    MAX_REDIRECTS = 3
    MAX_BYTES = 5 * 1024 * 1024
    USER_AGENT = "slot-availability/0.1 (+calendar import)"
