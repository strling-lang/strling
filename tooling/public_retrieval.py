"""Bounded, credential-free public reads; fixture authority stays synthetic."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class RetrievalError(ValueError):
    def __init__(
        self,
        category: str,
        detail: str,
        *,
        status: str = "FAILED",
        expected=None,
        observed=None,
    ):
        super().__init__(detail)
        self.category = category
        self.status = status
        self.expected = expected
        self.observed = observed


def resolve_addresses(host: str, port: int, timeout: float) -> list:
    """An OS resolver cannot overrun the download budget in the verifier process."""
    if timeout <= 0:
        raise TimeoutError("DNS deadline")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "PROGRAMDATA"}
    }
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                "import json,socket,sys; print(json.dumps(socket.getaddrinfo(sys.argv[1],int(sys.argv[2]),type=socket.SOCK_STREAM)))",
                host,
                str(port),
            ],
            capture_output=True,
            timeout=min(timeout, 30),
            check=True,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError("DNS deadline") from error
    except subprocess.SubprocessError as error:
        raise OSError("DNS lookup failed") from error
    return json.loads(completed.stdout)


def public_url(url: str, origins: set[str], *, timeout: float = 30) -> str:
    parsed = urllib.parse.urlsplit(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if (
        parsed.scheme != "https"
        or origin not in origins
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.port not in (None, 443)
        or any(ord(c) < 33 or ord(c) == 127 for c in url)
        or "\\" in url
    ):
        raise RetrievalError("security", "unapproved public retrieval location")
    try:
        addresses = resolve_addresses(parsed.hostname, 443, timeout)
    except (OSError, subprocess.SubprocessError) as error:
        raise RetrievalError(
            "registry-network", "DNS lookup failed", status="INDETERMINATE"
        ) from error
    if not addresses or any(
        not ipaddress.ip_address(row[4][0]).is_global for row in addresses
    ):
        raise RetrievalError(
            "security", "public registry resolved to a nonpublic address"
        )
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


class PublicHTTPSConnection(http.client.HTTPSConnection):
    """Connect to the validated public address without a second DNS resolution."""

    def connect(self):
        if self._tunnel_host is not None:
            raise RetrievalError("security", "public retrieval forbids proxy tunnels")
        deadline = time.monotonic() + self.timeout
        addresses = resolve_addresses(self.host, self.port, self.timeout)
        if not addresses or any(
            not ipaddress.ip_address(row[4][0]).is_global for row in addresses
        ):
            raise RetrievalError(
                "security", "connection resolved to a nonpublic address"
            )
        last = None
        for family, kind, protocol, _, address in addresses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("connection deadline")
            connection = socket.socket(family, kind, protocol)
            connection.settimeout(remaining)
            try:
                connection.connect(tuple(address))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("TLS deadline")
                connection.settimeout(remaining)
                self.sock = self._context.wrap_socket(
                    connection, server_hostname=self.host
                )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.sock.close()
                    raise TimeoutError("TLS deadline")
                self.sock.settimeout(remaining)
                return
            except OSError as error:
                last = error
                connection.close()
        raise last or OSError("no public connection address")


class PublicHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, request):
        return self.do_open(
            PublicHTTPSConnection, request, context=ssl.create_default_context()
        )


class PublicTransport:
    """GET only, no proxy/netrc/cookies/auth, exclusive retained response files."""

    authority = "public"

    def __init__(
        self, output: Path, origins: set[str], *, timeout: int = 30, attempts: int = 3
    ):
        if not 1 <= timeout <= 30 or not 1 <= attempts <= 3:
            raise ValueError("retrieval budget exceeds the governed bound")
        output.mkdir(parents=True, exist_ok=False)
        self.output = output
        self.origins = origins
        self.timeout = timeout
        self.attempts = attempts
        self.observations: list[dict] = []
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect(), PublicHTTPSHandler()
        )

    def _retain(self, observation: dict, body: bytes) -> bytes:
        index = len(self.observations)
        observation = {
            **observation,
            "authority": self.authority,
            "sha256": hashlib.sha256(body).hexdigest(),
            "size": len(body),
        }
        name = f"{index:05d}"
        with (self.output / (name + ".body")).open("xb") as stream:
            stream.write(body)
        observation["body"] = name + ".body"
        with (self.output / (name + ".json")).open(
            "x", encoding="utf-8", newline="\n"
        ) as stream:
            json.dump(observation, stream, sort_keys=True, indent=2)
            stream.write("\n")
        self.observations.append(observation)
        return body

    def get(self, url: str, *, maximum: int = 8 * 1024 * 1024) -> bytes:
        if not 0 < maximum <= 512 * 1024 * 1024:
            raise ValueError("invalid download bound")
        original = url
        redirects = 0
        for attempt in range(1, self.attempts + 1):
            deadline = time.monotonic() + self.timeout
            while True:
                public_url(url, self.origins, timeout=deadline - time.monotonic())
                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "STRling-independent-verifier/1",
                        "Accept-Encoding": "identity",
                    },
                    method="GET",
                )
                body = bytearray()
                observed_before = len(self.observations)
                response_status = None
                try:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("request deadline")
                    with self.opener.open(request, timeout=remaining) as response:
                        response_status = response.status
                        if (
                            response.status != 200
                            or response.headers.get("Content-Encoding", "identity")
                            != "identity"
                        ):
                            raise RetrievalError(
                                "registry-network",
                                "unexpected HTTP representation",
                                status="INDETERMINATE",
                            )
                        length = response.headers.get("Content-Length")
                        if length is not None and (
                            not length.isdecimal() or int(length) > maximum
                        ):
                            raise RetrievalError(
                                "security", "invalid or oversized HTTP content length"
                            )
                        while True:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                raise TimeoutError("download deadline")
                            live_socket = getattr(
                                getattr(getattr(response, "fp", None), "raw", None),
                                "_sock",
                                None,
                            )
                            if live_socket is not None:
                                live_socket.settimeout(remaining)
                            read = getattr(response, "read1", response.read)
                            chunk = read(min(65536, maximum + 1 - len(body)))
                            if not chunk:
                                break
                            body.extend(chunk)
                            if len(body) > maximum:
                                raise RetrievalError(
                                    "security", "oversized public payload"
                                )
                        if length is not None and len(body) != int(length):
                            self._retain(
                                {
                                    "request_url": original,
                                    "response_url": url,
                                    "http_status": 200,
                                    "attempt": attempt,
                                    "error_kind": "truncated-response",
                                },
                                bytes(body),
                            )
                            raise RetrievalError(
                                "registry-network",
                                "truncated public response",
                                status="INDETERMINATE",
                            )
                        return self._retain(
                            {
                                "request_url": original,
                                "response_url": url,
                                "http_status": 200,
                                "attempt": attempt,
                                "etag": response.headers.get("ETag"),
                                "last_modified": response.headers.get("Last-Modified"),
                            },
                            bytes(body),
                        )
                except urllib.error.HTTPError as error:
                    self._retain(
                        {
                            "request_url": original,
                            "response_url": url,
                            "http_status": error.code,
                            "attempt": attempt,
                        },
                        b"",
                    )
                    if error.code in (301, 302, 303, 307, 308):
                        redirects += 1
                        if redirects > 3 or not error.headers.get("Location"):
                            raise RetrievalError(
                                "security", "invalid redirect chain"
                            ) from error
                        url = urllib.parse.urljoin(url, error.headers["Location"])
                        continue
                    if error.code == 404:
                        raise RetrievalError(
                            "missing-coordinate",
                            "exact public coordinate is absent",
                            status="NOT_PUBLISHED",
                        ) from error
                    if error.code not in (408, 429, 500, 502, 503, 504):
                        raise RetrievalError(
                            "registry-network",
                            f"registry HTTP {error.code}",
                            status="INDETERMINATE",
                        ) from error
                    break
                except (
                    urllib.error.URLError,
                    TimeoutError,
                    OSError,
                    http.client.HTTPException,
                ) as error:
                    self._retain(
                        {
                            "request_url": original,
                            "response_url": url,
                            "http_status": None,
                            "attempt": attempt,
                            "error_kind": type(error).__name__,
                        },
                        bytes(body),
                    )
                    break
                except RetrievalError as error:
                    if len(self.observations) == observed_before:
                        self._retain(
                            {
                                "request_url": original,
                                "response_url": url,
                                "http_status": response_status,
                                "attempt": attempt,
                                "error_kind": error.category,
                            },
                            bytes(body),
                        )
                    raise
            if attempt < self.attempts:
                time.sleep(attempt)
        raise RetrievalError(
            "registry-network",
            "bounded retrieval attempts exhausted",
            status="INDETERMINATE",
        )


class FixtureTransport:
    """Explicit injected protocol responses; never a public authority."""

    authority = "synthetic"

    def __init__(self, responses: dict[str, bytes | RetrievalError]):
        self.responses = responses
        self.observations: list[dict] = []

    def get(self, url: str, *, maximum: int = 8 * 1024 * 1024) -> bytes:
        if url not in self.responses:
            raise RetrievalError("fixture-missing", "unregistered synthetic response")
        response = self.responses[url]
        if isinstance(response, RetrievalError):
            raise response
        if len(response) > maximum:
            raise RetrievalError("security", "oversized synthetic response")
        self.observations.append(
            {
                "authority": self.authority,
                "request_url": url,
                "sha256": hashlib.sha256(response).hexdigest(),
                "size": len(response),
            }
        )
        return response
