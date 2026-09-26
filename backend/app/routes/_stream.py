"""NDJSON streaming of real computations: each step event is emitted when the computation starts / finishes."""
from __future__ import annotations

import json
import queue
import threading
import traceback

from fastapi.responses import StreamingResponse

from ..db import SessionLocal

ERROR_FR = "L'analyse n'a pas pu aboutir. Veuillez réessayer."


def stream_job(job):
    """Run job(db, emit) in a worker thread and stream its events."""
    q: queue.Queue = queue.Queue()

    def worker():
        db = SessionLocal()
        try:
            q.put({"type": "result", "data": job(db, q.put)})
        except Exception:
            traceback.print_exc()
            q.put({"type": "error", "message": ERROR_FR})
        finally:
            db.close()
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        while True:
            ev = q.get()
            if ev is None:
                break
            yield json.dumps(ev, ensure_ascii=False, default=str) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def stream_text(emit, text: str, size: int = 22):
    for i in range(0, len(text), size):
        emit({"type": "text", "delta": text[i:i + size]})
