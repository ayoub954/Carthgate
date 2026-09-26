"""World Bank WDI provider — long annual macro series for Tunisia (used for history + forecasting)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .. import cache
from ..models import EconomicIndicator
from .base import CONNECTED, ERROR, DataProvider, ProviderStatus

INDICATORS = {
    "NE.IMP.GNFS.CN": ("wb_imports_gs", "Imports of goods & services (current TND)", "TND"),
    "NE.EXP.GNFS.CN": ("wb_exports_gs", "Exports of goods & services (current TND)", "TND"),
    "NY.GDP.MKTP.CN": ("wb_gdp", "GDP (current TND)", "TND"),
    "NE.IMP.GNFS.ZS": ("wb_imports_pct_gdp", "Imports of goods & services (% of GDP)", "%"),
    "GC.TAX.IMPT.CN": ("wb_customs_duties", "Customs and other import duties (current TND)", "TND"),
    "GC.TAX.IMPT.ZS": ("wb_customs_duties_pct_tax", "Customs & import duties (% of tax revenue)", "%"),
    "FP.CPI.TOTL.ZG": ("wb_inflation", "Inflation, consumer prices (annual %)", "%"),
}


class WorldBankProvider(DataProvider):
    key = "world_bank_wdi"
    name = "World Bank — World Development Indicators (Tunisia)"
    provider = "INSDataProvider"
    url = "https://data.worldbank.org/country/tunisia"
    access_type = "PUBLIC_OPEN_DATA"
    license = "CC BY 4.0"

    def health(self):
        ok = cache.exists("https://api.worldbank.org/v2/country/TUN?format=json")
        return ProviderStatus(self.key, CONNECTED if ok else ERROR)

    def ingest(self, db: Session, log) -> ProviderStatus:
        db.query(EconomicIndicator).filter(EconomicIndicator.source_key == self.key).delete()
        n, lo, hi = 0, 9999, 0
        for code, (ind, label, unit) in INDICATORS.items():
            url = f"https://api.worldbank.org/v2/country/TUN/indicator/{code}"
            try:
                resp = cache.fetch(url, params={"format": "json", "per_page": 100}, max_age_hours=24 * 7)
                self.register_raw(db, resp)
                rows = resp.json()[1] or []
            except Exception as e:
                log(f"World Bank {code}: {e}")
                continue
            for r in rows:
                if r["value"] is None:
                    continue
                y = int(r["date"])
                lo, hi = min(lo, y), max(hi, y)
                db.add(EconomicIndicator(indicator=ind, label=label, period=str(y), frequency="A",
                                         value=float(r["value"]), unit=unit, source_key=self.key,
                                         source_url=f"https://data.worldbank.org/indicator/{code}?locations=TN",
                                         retrieved_at=resp.retrieved_at))
                n += 1
        db.flush()
        st = ProviderStatus(self.key, CONNECTED if n else ERROR, f"{len(INDICATORS)} indicators", n,
                            period=f"{lo}–{hi}" if n else None, last_updated=datetime.utcnow())
        self.save_status(db, st)
        return st
