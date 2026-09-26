"""Institutional providers that require official access (RNE, SINDA, customs declarations, tariffs).

Without credentials these providers only check public reachability and report
ACCESS REQUIRED — they never fabricate registry or declaration data.
Declaration-level customs data can be loaded from an AUTHORIZED extract (CSV/XLSX)
through `import_customs_extract` (importer identifiers are hashed on ingestion).
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from .. import cache
from ..config import settings
from ..models import Business, CustomsImport
from .base import ACCESS_REQUIRED, CONNECTED, ERROR, DataProvider, ProviderStatus


class CustomsProvider(DataProvider):
    key = "douane_tn"
    name = "Douane Tunisienne — portail officiel"
    provider = "CustomsProvider"
    url = "https://www.douane.gov.tn/"
    access_type = "OFFICIAL_ACCESS"

    def health(self):
        ok = cache.exists(self.url)
        return ProviderStatus(self.key, CONNECTED if ok else ERROR,
                              "Public portal reachable. Declaration-level data requires SINDA / authorized extract."
                              if ok else "Portal unreachable")

    def ingest(self, db: Session, log) -> ProviderStatus:
        st = self.health()
        n = db.query(CustomsImport).count()
        if n:
            st.message = f"Authorized declaration extract loaded: {n} lines."
            st.records = n
        self.save_status(db, st)
        return st


class SINDAProvider(DataProvider):
    key = "sinda"
    name = "SINDA — Système d'information douanier (déclarations)"
    provider = "SINDAProvider"
    url = "https://www.douane.gov.tn/"
    access_type = "INSTITUTIONAL_ACCESS"

    def health(self):
        if settings.sinda_api_url and settings.sinda_api_key:
            try:
                r = httpx.get(settings.sinda_api_url, headers={"Authorization": f"Bearer {settings.sinda_api_key}"}, timeout=20)
                return ProviderStatus(self.key, CONNECTED if r.status_code < 400 else ERROR, f"HTTP {r.status_code}")
            except Exception as e:
                return ProviderStatus(self.key, ERROR, e.__class__.__name__)
        n_msg = "SINDA CONNECTION REQUIRED — declaration-level data (entry points, transport mode, importers, low-value shipments) is not publicly available."
        return ProviderStatus(self.key, ACCESS_REQUIRED, n_msg)

    def ingest(self, db: Session, log) -> ProviderStatus:
        st = self.health()
        n = db.query(CustomsImport).count()
        if n and st.status == ACCESS_REQUIRED:
            st = ProviderStatus(self.key, CONNECTED, f"Authorized extract loaded manually ({n} declaration lines)", n)
        self.save_status(db, st)
        return st


class RNEProvider(DataProvider):
    key = "rne"
    name = "RNE — Registre National des Entreprises"
    provider = "RNEProvider"
    url = "https://www.registre-entreprises.tn/"
    access_type = "INSTITUTIONAL_ACCESS"

    def health(self):
        if settings.rne_api_url and settings.rne_api_key:
            return ProviderStatus(self.key, CONNECTED, "RNE API configured")
        ok = cache.exists(self.url)
        return ProviderStatus(self.key, ACCESS_REQUIRED,
                              "RNE CONNECTION REQUIRED — public portal " + ("reachable" if ok else "unreachable") +
                              "; no bulk/API access without an institutional agreement. Business verification returns INSTITUTIONAL_ACCESS_REQUIRED.")

    def lookup(self, name: str) -> list[dict]:
        """Query the RNE API when institutional access is configured."""
        if not (settings.rne_api_url and settings.rne_api_key):
            return []
        r = httpx.get(settings.rne_api_url, params={"q": name},
                      headers={"Authorization": f"Bearer {settings.rne_api_key}"}, timeout=30)
        r.raise_for_status()
        return r.json().get("results", [])

    def ingest(self, db: Session, log) -> ProviderStatus:
        st = self.health()
        st.records = db.query(Business).count()
        self.save_status(db, st)
        return st


class TariffProvider(DataProvider):
    key = "tariff_tn"
    name = "Tarif douanier tunisien (Tarifs et nomenclatures)"
    provider = "TariffProvider"
    url = "https://www.douane.gov.tn/features/tarifs-et-nomenclatures/"
    access_type = "OFFICIAL_ACCESS"

    def health(self):
        ok = cache.exists(self.url)
        return ProviderStatus(self.key, ACCESS_REQUIRED if ok else ERROR,
                              "Tariff consultation is an interactive service; no machine-readable rate table is published. "
                              "Duty rates are not used in calculations (OFFICIAL ACCESS REQUIRED).")

    def ingest(self, db: Session, log) -> ProviderStatus:
        st = self.health()
        self.save_status(db, st)
        return st


# ---------------------------------------------------------------------------
REQUIRED = ["declaration_date", "hs_code", "declared_value"]
OPTIONAL = ["declaration_ref", "description", "importer_id", "origin_iso3", "provenance_iso3", "entry_point_id",
            "transport_mode", "quantity", "currency", "destination_governorate"]


def _h(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None
    return hashlib.sha256(str(v).strip().encode()).hexdigest()


def import_customs_extract(db: Session, content: bytes, filename: str, batch: str) -> dict:
    """Load an AUTHORIZED declaration extract. Importer IDs are hashed; raw IDs never stored."""
    if filename.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content))
    else:
        df = pd.read_csv(io.BytesIO(content))
    df.columns = [c.strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError("Colonnes obligatoires manquantes : " + ", ".join(missing) + ". Colonnes attendues : " + ", ".join(REQUIRED) + " (facultatives : " + ", ".join(OPTIONAL) + ").")
    mode_map = {"sea": "SEA", "mer": "SEA", "maritime": "SEA", "air": "AIR", "aerien": "AIR", "aérien": "AIR",
                "land": "LAND", "terre": "LAND", "terrestre": "LAND", "road": "LAND", "route": "LAND", "rail": "LAND"}
    n = 0
    for _, r in df.iterrows():
        mode = r.get("transport_mode")
        mode = mode_map.get(str(mode).strip().lower(), str(mode).upper()) if isinstance(mode, str) else None
        db.add(CustomsImport(
            declaration_ref_hash=_h(r.get("declaration_ref")), declaration_date=pd.to_datetime(r["declaration_date"]).to_pydatetime(),
            hs_code=str(r["hs_code"]).replace(".", "").strip(), description=r.get("description") if isinstance(r.get("description"), str) else None,
            importer_hash=_h(r.get("importer_id")), origin_iso3=r.get("origin_iso3") if isinstance(r.get("origin_iso3"), str) else None,
            provenance_iso3=r.get("provenance_iso3") if isinstance(r.get("provenance_iso3"), str) else None,
            entry_point_id=r.get("entry_point_id") if isinstance(r.get("entry_point_id"), str) else None,
            transport_mode=mode if mode in ("SEA", "AIR", "LAND") else None,
            quantity=float(r["quantity"]) if "quantity" in r and pd.notna(r.get("quantity")) else None,
            declared_value=float(r["declared_value"]), currency=r.get("currency") if isinstance(r.get("currency"), str) else "TND",
            destination_governorate=r.get("destination_governorate") if isinstance(r.get("destination_governorate"), str) else None,
            import_batch=batch, source_key="authorized_customs_extract", source_url=f"upload:{filename}",
            retrieved_at=datetime.utcnow()))
        n += 1
    db.flush()
    return {"rows": n, "batch": batch}
