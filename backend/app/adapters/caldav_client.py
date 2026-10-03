from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import httpx


class CalDavError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CalDavAuthError(CalDavError):
    pass


class CalDavClient:
    def __init__(
        self,
        origin: str,
        authorization: str,
        timeout: float | None = None,
    ) -> None:
        resolved_timeout = Constants.TIMEOUT_SECONDS if timeout is None else timeout
        self._origin = origin.rstrip("/")
        self._authorization = authorization
        self._client = httpx.Client(
            timeout=resolved_timeout,
            follow_redirects=False,
            headers={
                "Authorization": authorization,
                "User-Agent": Constants.USER_AGENT,
            },
        )

    def close(self) -> None:
        self._client.close()

    def discover_calendars(self) -> list[tuple[str, str]]:
        start_url = f"{self._origin}{Constants.WELL_KNOWN_PATH}"
        principal = self._find_property_href(
            start_url,
            Constants.DAV_NS,
            "current-user-principal",
        ) or self._find_property_href(
            f"{self._origin}/",
            Constants.DAV_NS,
            "current-user-principal",
        )
        if principal is None:
            principal = f"{self._origin}/"
        principal_url = self._absolute(principal, start_url)
        home = self._find_property_href(
            principal_url,
            Constants.CALDAV_NS,
            "calendar-home-set",
        )
        if home is None:
            raise CalDavError("Не удалось найти calendar-home-set")
        home_url = self._absolute(home, principal_url)
        return self._list_calendars(home_url)

    def fetch_calendar_data(self, calendar_url: str, start_utc: str, end_utc: str) -> list[str]:
        body = Constants.CALENDAR_QUERY.format(start=start_utc, end=end_utc)
        response = self._request(
            "REPORT",
            calendar_url,
            content=body,
            headers={
                "Content-Type": "application/xml; charset=utf-8",
                "Depth": "1",
            },
        )
        root = ET.fromstring(response.content)
        payloads: list[str] = []
        for data in root.findall(".//{%s}calendar-data" % Constants.CALDAV_NS):
            if data.text:
                payloads.append(data.text)
        return payloads

    def _list_calendars(self, home_url: str) -> list[tuple[str, str]]:
        body = Constants.PROPFIND_CALENDAR
        response = self._request(
            "PROPFIND",
            home_url,
            content=body,
            headers={
                "Content-Type": "application/xml; charset=utf-8",
                "Depth": "1",
            },
        )
        root = ET.fromstring(response.content)
        found: list[tuple[str, str]] = []
        for response_el in root.findall("{%s}response" % Constants.DAV_NS):
            href_el = response_el.find("{%s}href" % Constants.DAV_NS)
            if href_el is None or not href_el.text:
                continue
            if response_el.find(".//{%s}calendar" % Constants.CALDAV_NS) is None:
                continue
            if _is_scheduling_collection(response_el):
                continue
            name_el = response_el.find(".//{%s}displayname" % Constants.DAV_NS)
            name = (name_el.text or "").strip() or href_el.text.rstrip("/").rsplit("/", 1)[-1]
            found.append((self._absolute(href_el.text, home_url), name))
        return found

    def _find_property_href(self, url: str, namespace: str, local_name: str) -> str | None:
        prefix = "c" if namespace == Constants.CALDAV_NS else "d"
        body = Constants.PROPFIND_NAMED.format(prefix=prefix, name=local_name)
        try:
            response = self._request(
                "PROPFIND",
                url,
                content=body,
                headers={
                    "Content-Type": "application/xml; charset=utf-8",
                    "Depth": "0",
                },
            )
        except CalDavError:
            return None
        root = ET.fromstring(response.content)
        prop = root.find(f".//{{{namespace}}}{local_name}")
        if prop is None:
            return None
        href = prop.find("{%s}href" % Constants.DAV_NS)
        if href is not None and href.text:
            return href.text
        return None

    def _request(self, method: str, url: str, content: str, headers: dict[str, str]) -> httpx.Response:
        current = url
        body = content.encode("utf-8")
        for _ in range(Constants.MAX_REDIRECTS):
            response = self._client.request(method, current, content=body, headers=headers)
            if response.status_code in Constants.REDIRECT_STATUSES:
                location = response.headers.get("Location")
                if not location:
                    break
                current = self._absolute(location, current)
                continue
            if response.status_code in Constants.AUTH_STATUSES:
                raise CalDavAuthError("Провайдер отклонил вход", status_code=response.status_code)
            if response.status_code >= 400:
                raise CalDavError(
                    f"CalDAV {method} {current} → {response.status_code}",
                    status_code=response.status_code,
                )
            return response
        raise CalDavError(f"CalDAV {method} {url} слишком много редиректов")

    def _absolute(self, href: str, base: str) -> str:
        if href.startswith("http://") or href.startswith("https://"):
            return href
        joined = urljoin(base if base.endswith("/") else base + "/", href)
        parsed = urlparse(joined)
        if parsed.scheme:
            return joined
        return urljoin(self._origin + "/", href.lstrip("/"))


def _is_scheduling_collection(response_el: ET.Element) -> bool:
    for tag in (Constants.INBOX, Constants.OUTBOX, Constants.NOTIFICATION):
        if response_el.find(f".//{tag}") is not None:
            return True
    return False


class Constants:
    TIMEOUT_SECONDS = 20.0
    USER_AGENT = "slot-availability/0.1"
    WELL_KNOWN_PATH = "/.well-known/caldav"
    DAV_NS = "DAV:"
    CALDAV_NS = "urn:ietf:params:xml:ns:caldav"
    INBOX = "{urn:ietf:params:xml:ns:caldav}schedule-inbox"
    OUTBOX = "{urn:ietf:params:xml:ns:caldav}schedule-outbox"
    NOTIFICATION = "{http://calendarserver.org/ns/}notification"
    AUTH_STATUSES = {401, 403}
    REDIRECT_STATUSES = {301, 302, 303, 307, 308}
    MAX_REDIRECTS = 6
    PROPFIND_NAMED = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop><{prefix}:{name}/></d:prop>
</d:propfind>
"""
    PROPFIND_CALENDAR = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:displayname/>
    <d:resourcetype/>
  </d:prop>
</d:propfind>
"""
    CALENDAR_QUERY = """<?xml version="1.0" encoding="UTF-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:getetag/>
    <c:calendar-data>
      <c:comp name="VCALENDAR">
        <c:comp name="VEVENT">
          <c:prop name="UID"/>
          <c:prop name="DTSTART"/>
          <c:prop name="DTEND"/>
          <c:prop name="DURATION"/>
          <c:prop name="RRULE"/>
          <c:prop name="RDATE"/>
          <c:prop name="EXDATE"/>
          <c:prop name="STATUS"/>
          <c:prop name="TRANSP"/>
          <c:prop name="RECURRENCE-ID"/>
        </c:comp>
      </c:comp>
    </c:calendar-data>
  </d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT">
        <c:time-range start="{start}" end="{end}"/>
      </c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>
"""
