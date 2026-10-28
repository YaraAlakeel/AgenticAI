"""A small web UI for the same agent:   uv run web.py   ->  http://127.0.0.1:8000

The page sends a task, polls /api/state for events, and shows an
Approve / Reject card whenever the agent wants to write a file.
One run at a time; the agent works in ./playground (a copy of ./demo).
"""

import asyncio
import threading
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import agent

app = FastAPI(title="tiny-coder")
state = {"running": False, "events": [], "pending": None, "decision": False}
decided = threading.Event()


def on_event(kind: str, data) -> None:
    state["events"].append({"kind": kind, "data": data})


def approve_in_browser(name: str, args: dict) -> bool:
    """Called from the agent thread: show the card, wait for the click (max 5 min)."""
    state["pending"] = {"name": name, "args": args}
    decided.clear()
    ok = decided.wait(timeout=300) and state["decision"]
    state["pending"] = None
    return ok


def run_in_background(task: str, config: str) -> None:
    try:
        r = asyncio.run(agent.run_agent(task, agent.playground(), config,
                                        approve=approve_in_browser, on_event=on_event))
        on_event("summary", f"{r['stop']} | steps={r['steps']} tokens={r['tokens']} cost=${r['cost']:.4f}")
    except Exception as e:
        on_event("error", f"{type(e).__name__}: {e}")
    finally:
        state["running"] = False


class Run(BaseModel):
    task: str
    config: str = "solve-with-test-loop"


class Decision(BaseModel):
    ok: bool


@app.get("/")
def page():
    return FileResponse(Path(__file__).parent / "web" / "index.html")


@app.post("/api/run")
def run(body: Run):
    if state["running"]:
        raise HTTPException(409, "a run is already in progress")
    state.update(running=True, events=[], pending=None)
    threading.Thread(target=run_in_background, args=(body.task, body.config), daemon=True).start()
    return {"ok": True}


@app.get("/api/state")
def get_state():
    return {"running": state["running"], "events": state["events"], "pending": state["pending"],
            "model": agent.MODEL}


@app.post("/api/approve")
def approve(body: Decision):
    state["decision"] = body.ok
    decided.set()
    return {"ok": True}


@app.post("/api/reset")
def reset():
    if state["running"]:
        raise HTTPException(409, "wait for the run to finish")
    agent.playground(reset=True)
    state["events"] = []
    return {"ok": True}


@app.get("/api/files")
def files():
    pg = agent.playground()
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(pg.glob("*")) if p.is_file()}


if __name__ == "__main__":
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
