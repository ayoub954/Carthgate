"""DBSCAN geographic clustering of public commercial locations."""
from __future__ import annotations

from collections import Counter

import numpy as np
from sklearn.cluster import DBSCAN
from sqlalchemy.orm import Session

from ..models import Cluster, Seller

EARTH_KM = 6371.0


def geo_clusters(db: Session, log=print, eps_km: float = 1.2, min_samples: int = 8) -> str:
    sellers = db.query(Seller).filter(Seller.lat.isnot(None)).all()
    if len(sellers) < min_samples:
        return "INSUFFICIENT DATA"
    X = np.radians([[s.lat, s.lon] for s in sellers])
    labels = DBSCAN(eps=eps_km / EARTH_KM, min_samples=min_samples, metric="haversine", algorithm="ball_tree").fit_predict(X)
    db.query(Cluster).filter(Cluster.kind == "GEO_COMMERCIAL").delete()
    for s, l in zip(sellers, labels):
        s.geo_cluster = int(l) if l >= 0 else None
    groups: dict[int, list[Seller]] = {}
    for s, l in zip(sellers, labels):
        if l >= 0:
            groups.setdefault(int(l), []).append(s)
    for l, members in groups.items():
        cats = Counter(m.category for m in members if m.category)
        govs = Counter(m.governorate for m in members if m.governorate)
        cities = Counter(m.city for m in members if m.city)
        gov = govs.most_common(1)[0][0] if govs else "Unknown governorate"
        label = f"{cities.most_common(1)[0][0] if cities else gov} — {cats.most_common(1)[0][0] if cats else 'mixed'}"
        db.add(Cluster(kind="GEO_COMMERCIAL", label=label, size=len(members),
                       centroid_lat=float(np.mean([m.lat for m in members])), centroid_lon=float(np.mean([m.lon for m in members])),
                       params={"algorithm": "DBSCAN", "metric": "haversine", "eps_km": eps_km, "min_samples": min_samples},
                       summary={"governorate": gov, "categories": dict(cats.most_common(6)),
                                "cluster_id": l, "source": "OpenStreetMap shops"}))
    db.flush()
    noise = int((labels < 0).sum())
    return f"{len(groups)} geographic commercial clusters (eps={eps_km} km, min={min_samples}); {noise} isolated points"
