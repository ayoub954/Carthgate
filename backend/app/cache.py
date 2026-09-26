"""Local data cache: avoid re-downloading the same source; keep provenance + checksum."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib import robotparser

import ssl

import httpx
import truststore

from .config import CACHE_DIR, settings

# verify TLS against the OS trust store (some official .tn sites ship incomplete chains)
SSL_CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

_robots: dict[str, robotparser.RobotFileParser] = {}
_last_hit: dict[str, float] = {}


@dataclass
class CachedResponse:
    url: str
    content: bytes
    retrieved_at: datetime
    checksum: str
    path: Path
    from_cache: bool
    content_type: str | None = None

    def json(self):
        return json.loads(self.content.decode("utf-8"))

    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


def _key(url: str, body: str | None) -> str:
    return hashlib.sha256((url + "|" + (body or "")).encode()).hexdigest()[:40]


def robots_allowed(url: str) -> bool:
    """Respect robots.txt for every non-API web page we observe."""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    rp = _robots.get(base)
    if rp is None:
        rp = robotparser.RobotFileParser()
        try:
            r = httpx.get(base + "/robots.txt", timeout=20, verify=SSL_CTX, headers={"User-Agent": settings.user_agent}, follow_redirects=True)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _robots[base] = rp
    return rp.can_fetch(settings.user_agent, url)


def _throttle(host: str, min_interval: float) -> None:
    last = _last_hit.get(host, 0)
    wait = min_interval - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()


def fetch(
    url: str,
    *,
    params: dict | None = None,
    data: dict | None = None,
    max_age_hours: float = 24 * 7,
    force: bool = False,
    check_robots: bool = False,
    min_interval: float = 1.0,
    headers: dict | None = None,
    timeout: float | None = None,
) -> CachedResponse:
    """GET (or POST form when `data`) with a disk cache. Raises on HTTP errors."""
    full = str(httpx.URL(url, params=params)) if params else url
    body = json.dumps(data, sort_keys=True) if data else None
    k = _key(full, body)
    path = CACHE_DIR / f"{k}.bin"
    meta_path = CACHE_DIR / f"{k}.json"
    if not force and path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text("utf-8"))
        ts = datetime.fromisoformat(meta["retrieved_at"])
        if (datetime.utcnow() - ts).total_seconds() < max_age_hours * 3600:
            content = path.read_bytes()
            return CachedResponse(full, content, ts, meta["checksum"], path, True, meta.get("content_type"))
    if check_robots and not robots_allowed(full):
        raise PermissionError(f"robots.txt disallows {full}")
    _throttle(urlparse(full).netloc, min_interval)
    h = {"User-Agent": settings.user_agent}
    if headers:
        h.update(headers)
    r = None
    for attempt in range(4):
        try:
            with httpx.Client(timeout=timeout or settings.http_timeout, follow_redirects=True, headers=h, verify=SSL_CTX) as c:
                r = c.post(url, data=data, params=params) if data else c.get(url, params=params)
            if r.status_code in (429, 502, 503, 504) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            break
        except (httpx.TransportError,) as e:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    content = r.content
    checksum = hashlib.sha256(content).hexdigest()
    now = datetime.utcnow()
    path.write_bytes(content)
    meta_path.write_text(
        json.dumps({"url": full, "retrieved_at": now.isoformat(), "checksum": checksum,
                    "content_type": r.headers.get("content-type")}),
        "utf-8",
    )
    return CachedResponse(full, content, now, checksum, path, False, r.headers.get("content-type"))


def exists(url: str, min_interval: float = 0.5) -> bool:
    try:
        _throttle(urlparse(url).netloc, min_interval)
        r = httpx.head(url, timeout=20, follow_redirects=True, verify=SSL_CTX, headers={"User-Agent": settings.user_agent})
        return r.status_code < 400
    except Exception:
        return False
