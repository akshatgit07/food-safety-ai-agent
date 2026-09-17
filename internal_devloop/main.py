from __future__ import annotations

from contextlib import asynccontextmanager
from html import escape

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from .models import FeatureRunRequest, HumanDecisionRequest
from .service import DevLoopService, default_db_path


service = DevLoopService(default_db_path())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    service.close()


app = FastAPI(title="Guiltless Internal Feature Loop", version="0.1.0", lifespan=lifespan,
              description="Prototype control plane. Mock providers only; no production code or deployment mutation.")


@app.get("/health")
def health():
    return {"healthy": True, "service": "internal-feature-loop", "execution_mode": "mock"}


@app.post("/runs", status_code=201)
def create_run(request: FeatureRunRequest):
    return service.create_run(request)


@app.get("/runs")
def list_runs(status: str | None = Query(default=None)):
    return {"runs": service.list_runs(status), "count": len(service.list_runs(status))}


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    run = service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/runs/{run_id}/decisions")
def submit_decision(run_id: str, request: HumanDecisionRequest):
    try:
        run, duplicate = service.decide(run_id, request)
        return {"duplicate": duplicate, "run": run}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/approvals/pending")
def pending_approvals():
    runs = service.list_runs("needs_approval")
    return {"approvals": [{"run_id": run["run_id"], **(run["blocker"] or {})} for run in runs], "count": len(runs)}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    rows = service.list_runs()
    rendered = "".join(
        f"<tr><td><a href='/runs/{escape(run['run_id'])}'>{escape(run['run_id'][:8])}</a></td>"
        f"<td>{escape(run['status'])}</td><td>{escape(run['feature_request'][:90])}</td>"
        f"<td>{len(run['state'].get('tasks', []))}</td><td>{escape(str((run.get('blocker') or {}).get('reason', '—')))}</td></tr>"
        for run in rows
    )
    return f"""<!doctype html><html><head><title>Guiltless Dev Loop</title><style>
    body{{font:14px system-ui;margin:40px;background:#f4f7f3;color:#173c29}}table{{width:100%;border-collapse:collapse;background:white}}
    th,td{{padding:12px;border-bottom:1px solid #dce8df;text-align:left}}.notice{{padding:14px;background:#fff4cc;border-radius:10px}}
    </style></head><body><h1>Guiltless autonomous feature loop</h1><p class='notice'>Prototype control plane · mock execution · no production mutations</p>
    <p>Active and completed runs: {len(rows)} · <a href='/approvals/pending'>Pending approvals</a></p>
    <table><thead><tr><th>Run</th><th>Status</th><th>Feature</th><th>Tasks</th><th>Blocker</th></tr></thead><tbody>{rendered}</tbody></table></body></html>"""
