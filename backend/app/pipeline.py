"""Pipeline: OBSERVE → COLLECT → NORMALIZE → MATCH → DETECT → ANALYZE → SCORE → EXPLAIN → RECOMMEND.

Run:  python -m app.pipeline            (all providers + analytics)
      python -m app.pipeline analytics  (analytics only, using cached/DB data)
"""
from __future__ import annotations

import sys
import threading
import time
import traceback
from datetime import datetime

from .db import init_db, session_scope
from .models import PipelineRun

_lock = threading.Lock()
STATE = {"running": False, "step": None, "started_at": None, "log": []}


def _log(msg: str):
    line = f"{datetime.utcnow().strftime('%H:%M:%S')} {msg}"
    STATE["log"].append(line)
    STATE["log"] = STATE["log"][-300:]
    print(line, flush=True)


def run_providers(only: list[str] | None = None):
    from .providers.comtrade import seed_products
    from .providers.registry import all_providers

    for p in all_providers():
        if only and p.key not in only:
            continue
        STATE["step"] = f"provider:{p.key}"
        t = time.time()
        try:
            with session_scope() as db:
                st = p.ingest(db, _log)
                if p.key == "hs_nomenclature":
                    seed_products(db)
            _log(f"[{p.key}] {st.status} — {st.records} records — {st.message[:160]} ({time.time()-t:.1f}s)")
        except Exception as e:
            _log(f"[{p.key}] ERROR {e}")
            traceback.print_exc()
            try:
                from .providers.base import ERROR, ProviderStatus
                with session_scope() as db:
                    p.save_status(db, ProviderStatus(p.key, ERROR, str(e)[:500]))
            except Exception:
                pass


def run_analytics(mode: str = "REAL", only: list[str] | None = None):
    from .services import analytics

    for name, fn in analytics.STEPS:
        if only and name not in only:
            continue
        STATE["step"] = f"analytics:{name}"
        t = time.time()
        try:
            with session_scope(mode) as db:
                msg = fn(db, _log)
            _log(f"[{name}] OK {msg or ''} ({time.time()-t:.1f}s)")
        except Exception as e:
            _log(f"[{name}] ERROR {e}")
            traceback.print_exc()


def run_all(providers: bool = True, analytics_: bool = True):
    if not _lock.acquire(blocking=False):
        return False
    STATE.update(running=True, started_at=datetime.utcnow().isoformat(), log=[])
    run_id = None
    status = "ERROR"
    try:
        init_db()
        with session_scope() as db:
            r = PipelineRun(status="RUNNING")
            db.add(r)
            db.flush()
            run_id = r.id
        if providers:
            run_providers()
        if analytics_:
            run_analytics()
        status = "DONE"
    except Exception as e:
        _log(f"pipeline failed: {e}")
        status = "ERROR"
    finally:
        with session_scope() as db:
            r = db.get(PipelineRun, run_id) if run_id else None
            if r:
                r.status, r.finished_at, r.log = status, datetime.utcnow(), STATE["log"][-200:]
        STATE.update(running=False, step=None)
        _lock.release()
    return True


def run_in_background(providers=True, analytics_=True) -> bool:
    if STATE["running"]:
        return False
    threading.Thread(target=run_all, kwargs={"providers": providers, "analytics_": analytics_}, daemon=True).start()
    return True


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg == "analytics":
        run_all(providers=False)
    elif arg == "providers":
        run_all(analytics_=False)
    elif arg.startswith("only="):
        init_db()
        run_providers(arg[5:].split(","))
    else:
        run_all()
