"""Scoped compatibility seam for garminconnect 0.3.17's synchronous HTTP clients.

Intercept actual requests, including login fingerprint loops and redirects. No
patch is installed at import time. This CLI is single-threaded; embedding it in a
multi-threaded application is not supported. Secrets are inspected only in memory
to identify refresh grants, and are never copied into error messages or logs.
"""

import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from curl_cffi import requests as curl_requests

from .errors import AppError, TransportStop
from .models import utcnow


def retry_time(value: str | None, now: datetime | None = None) -> str:
    moment = now or utcnow()
    try:
        seconds = int(value or "")
        result = moment + timedelta(seconds=max(0, min(seconds, 86400)))
    except ValueError:
        try:
            result = parsedate_to_datetime(value or "").astimezone(UTC)
            result = min(max(result, moment), moment + timedelta(days=1))
        except (TypeError, ValueError, OverflowError):
            result = moment + timedelta(minutes=15)
    return result.isoformat()


class RequestGuard:
    def __init__(self, region: str, *, limit: int = 256, seconds: int = 180):
        self.domain = "garmin.cn" if region == "cn" else "garmin.com"
        self.limit = limit
        self.deadline = time.monotonic() + seconds
        self.count = 0
        self.refreshes = 0
        self.unauthorized = 0
        self.stopped: AppError | None = None

    def stop(self, code: str, retry_at: str | None = None):
        self.stopped = AppError(code, retry_at)
        raise TransportStop(self.stopped)

    def before(self, method: str, url: str, body=None):
        if self.stopped:
            raise TransportStop(self.stopped)
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not (
            host == self.domain or host.endswith("." + self.domain)
        ):
            self.stop("INPUT_MISMATCH")
        if host == "connectapi." + self.domain and method.upper() != "GET":
            if method.upper() != "POST" or parsed.path != "/graphql-gateway/graphql":
                self.stop("UNSUPPORTED")
        if self.count >= self.limit or time.monotonic() >= self.deadline:
            self.stop("REQUEST_BUDGET")
        data = body
        if isinstance(body, (str, bytes)):
            if isinstance(body, bytes):
                body = body.decode("utf-8", errors="replace")
            data = parse_qs(body)
        grant = data.get("grant_type") if isinstance(data, dict) else None
        if grant in ("refresh_token", ["refresh_token"]):
            self.refreshes += 1
            if self.refreshes > 1:
                self.stop("AUTH_REQUIRED")
        self.count += 1

    def after(self, response, url: str):
        status = response.status_code
        if status == 429:
            self.stop("RATE_LIMITED", retry_time(response.headers.get("Retry-After")))
        if status >= 500:
            # The engine may make one explicit retry, never the library's fallback loops.
            raise TransportStop(AppError("NETWORK_ERROR"))
        if status == 401:
            if urlparse(url).hostname != "connectapi." + self.domain:
                if "mfa" in urlparse(url).path.lower():
                    return
                self.stop("AUTH_FAILED")
            self.unauthorized += 1
            if self.unauthorized > 1 or self.refreshes:
                self.stop("AUTH_REQUIRED")
        elif status == 403:
            self.stop("FORBIDDEN")
        elif status >= 400 and urlparse(url).hostname == "connectapi." + self.domain:
            code = "UNSUPPORTED" if status in {404, 410} else "INVALID_RESPONSE"
            raise TransportStop(AppError(code))
        elif status >= 400 and "di-oauth2-service" in url and self.refreshes:
            self.stop("AUTH_REQUIRED")
        # Some Garmin login endpoints bury 429 in a successful HTTP response.
        if (
            urlparse(url).hostname != "connectapi." + self.domain
            or "json" in response.headers.get("Content-Type", "").lower()
        ):
            try:
                data = response.json()
            except (ValueError, TypeError):
                return
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict) and str(error.get("status-code")) == "429":
                self.stop("RATE_LIMITED", retry_time(None))

    @contextmanager
    def scope(self):
        original_send = requests.Session.send
        original_curl = curl_requests.Session.request
        original_netrc = requests.sessions.get_netrc_auth
        guard = self

        def send(session, request, **kwargs):
            guard.before(request.method, request.url, request.body)
            kwargs["timeout"] = min(15, max(1, guard.deadline - time.monotonic()))
            try:
                response = original_send(session, request, **kwargs)
            except requests.RequestException:
                raise TransportStop(AppError("NETWORK_ERROR")) from None
            guard.after(response, request.url)
            return response

        def curl_request(session, method, url, **kwargs):
            follow = kwargs.pop("allow_redirects", True)
            kwargs["allow_redirects"] = False
            for _ in range(6):
                guard.before(method, url, kwargs.get("data") or kwargs.get("json"))
                kwargs["timeout"] = min(15, max(1, guard.deadline - time.monotonic()))
                try:
                    response = original_curl(session, method, url, **kwargs)
                except curl_requests.RequestsError:
                    raise TransportStop(AppError("NETWORK_ERROR")) from None
                guard.after(response, url)
                if not follow or response.status_code not in {301, 302, 303, 307, 308}:
                    return response
                location = response.headers.get("Location")
                if not location:
                    return response
                url = urljoin(url, location)
                kwargs.pop("params", None)
                if response.status_code == 303 or (
                    response.status_code in {301, 302} and method.upper() == "POST"
                ):
                    method = "GET"
                    kwargs.pop("data", None)
                    kwargs.pop("json", None)
            guard.stop("REQUEST_BUDGET")

        requests.Session.send = send
        curl_requests.Session.request = curl_request
        requests.sessions.get_netrc_auth = lambda *args, **kwargs: None
        try:
            yield
        finally:
            requests.Session.send = original_send
            curl_requests.Session.request = original_curl
            requests.sessions.get_netrc_auth = original_netrc
