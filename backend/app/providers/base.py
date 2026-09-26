"""DataProvider architecture. Providers never fabricate data: they return real rows or a status."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..cache import CachedResponse
from ..models import DataSource, RawRecord

# Status vocabulary shown in the Data Source Center
CONNECTED = "CONNECTED"
AVAILABLE = "AVAILABLE"
ERROR = "ERROR"
ACCESS_REQUIRED = "ACCESS REQUIRED"
NOT_AVAILABLE = "NOT AVAILABLE"


@dataclass
class ProviderStatus:
    key: str
    status: str
    message: str = ""
    records: int = 0
    period: str | None = None
    last_updated: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class DataProvider:
    key: str = "base"
    name: str = "Base provider"
    provider: str = "base"
    url: str = ""
    access_type: str = "PUBLIC_OPEN_DATA"
    license: str | None = None

    def health(self) -> ProviderStatus:  # cheap reachability check
        raise NotImplementedError

    def ingest(self, db: Session, log) -> ProviderStatus:  # download + normalise + store
        raise NotImplementedError

    # ---- helpers -------------------------------------------------------
    def register_raw(self, db: Session, resp: CachedResponse, period: str | None = None,
                     last_updated: str | None = None) -> None:
        if resp.from_cache and db.query(RawRecord).filter_by(checksum=resp.checksum).first():
            return
        db.add(RawRecord(source_key=self.key, source_url=resp.url, retrieved_at=resp.retrieved_at,
                         cache_path=str(resp.path), checksum=resp.checksum,
                         content_type=resp.content_type, period=period, last_updated=last_updated,
                         size_bytes=len(resp.content)))

    def save_status(self, db: Session, st: ProviderStatus, name: str | None = None, url: str | None = None) -> None:
        ds = db.query(DataSource).filter_by(key=st.key).first()
        if ds is None:
            ds = DataSource(key=st.key, name=name or self.name, provider=self.provider, url=url or self.url,
                            access_type=self.access_type, status=st.status)
            db.add(ds)
        ds.name, ds.provider, ds.url, ds.access_type = name or self.name, self.provider, url or self.url, self.access_type
        ds.status, ds.message, ds.records, ds.period = st.status, st.message, st.records, st.period
        ds.license = self.license
        ds.last_checked = datetime.utcnow()
        if st.last_updated:
            ds.last_updated = st.last_updated
        db.flush()
