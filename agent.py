"""tiny-coder: a minimal coding-agent harness.

    uv run agent.py "The tests fail. Find the bug and fix it."

The file follows the parts of a harness from the course, top to bottom:
  1. CONFIG   budgets and the two eval configurations (solve-no-test-loop / solve-with-test-loop)
  2. CONTEXT  AGENTS.md + memory notes -> system prompt, and the compaction rule
  3. TOOLS    3 MCP tools (workspace_server.py) + 2 local tools
  4. POLICY   allow / ask / deny for every tool call, plus an audit log
  5. LOOP     the agent loop with step, token and cost budgets
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

# ----------------------------------------------------------------- 1. CONFIG
MODEL = os.getenv("MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")  # tried if MODEL errors
MAX_STEPS = 12            # model calls per task
MAX_TOKENS = 80_000       # prompt + completion tokens per task
MAX_COST_USD = 0.05       # per task (free models report $0)
MAX_OUTPUT_TOKENS = 4_096 # per model reply (also caps what OpenRouter reserves per call)
MAX_RESULT_CHARS = 3_000  # cap on any single tool result
KEEP_FULL_RESULTS = 4     # older tool results are compacted to a stub
NOTES_FILE = "NOTES.md"   # the agent's memory, kept inside the workspace

CONFIGS = {
    "solve-no-test-loop": {"run_tests": False},   # baseline (A): the agent can only read and write
    "solve-with-test-loop": {"run_tests": True},  # the one change (B): it can run the tests and retry
}

# ---------------------------------------------------------------- 2. CONTEXT
def system_prompt(workspace: Path) -> str:
    """Context file (AGENTS.md) + memory from earlier runs (capped)."""
    prompt = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    notes = workspace / NOTES_FILE
    if notes.exists():
        prompt += "\n\n## Your notes from earlier runs\n" + notes.read_text(encoding="utf-8")[-2000:]
    return prompt


def clip(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    """Budget rule: keep the head and tail of long tool output, cut the middle."""
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n...[{len(text) - limit} chars cut]...\n{text[-half:]}"


def compact(messages: list[dict]) -> None:
    """Compaction rule: only the last few tool results stay in full."""
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    for m in tool_msgs[:-KEEP_FULL_RESULTS]:
        if not m["content"].startswith("[compacted]"):
            m["content"] = "[compacted] " + m["content"][:200]

# ------------------------------------------------------------------ 3. TOOLS
# list_files, read_file and write_file come from the MCP server.
LOCAL_TOOLS = {
    "run_tests": {
        "description": "Run the project's pytest suite. Returns PASSED or FAILED plus the output.",
        "parameters": {"type": "object", "properties": {}},
    },
    "save_note": {
        "description": "Save a short note to your memory. You will see it again in later runs.",
        "parameters": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]},
    },
}


def safe_env() -> dict:
    """Child processes never inherit API keys or tokens."""
    return {k: v for k, v in os.environ.items()
            if not any(word in k.upper() for word in ("KEY", "TOKEN", "SECRET"))}


def run_tests(workspace: Path) -> str:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(workspace)],
            cwd=workspace, capture_output=True, text=True, timeout=60, env=safe_env())
    except subprocess.TimeoutExpired:
        return "FAILED: tests timed out after 60s"
    status = "PASSED" if r.returncode == 0 else f"FAILED (exit code {r.returncode})"
    return f"{status}\n{r.stdout}{r.stderr}"


def save_note(workspace: Path, note: str) -> str:
    with open(workspace / NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(f"- {note}\n")
    return "noted"


def as_openai_tool(name: str, description: str, parameters: dict) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


@asynccontextmanager
async def mcp_session(workspace: Path, jail: bool = True):
    """Start workspace_server.py as a subprocess and talk MCP to it over stdio."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "workspace_server.py"), str(workspace)],
        env={**safe_env(), "WORKSPACE_JAIL": "on" if jail else "off"})
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session

# ----------------------------------------------------------------- 4. POLICY
def policy(name: str, args: dict) -> tuple[str, str]:
    """allow / ask / deny for every tool call. Enforced in code, not in the prompt."""
    if name == "write_file":
        file = Path(args.get("path", "")).name
        if file.startswith("test_") or file.endswith("_test.py"):
            return "deny", "test files are read-only"
        return "ask", "writes need human approval"
    return "allow", ""  # reads, tests and notes are low risk


def audit(**event) -> None:
    log = ROOT / "logs" / "audit.jsonl"
    log.parent.mkdir(exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": round(time.time(), 3), **event}) + "\n")


def ask_in_terminal(name: str, args: dict) -> bool:
    print(f"\n  !! approval needed: {name} {args.get('path', '')}")
    for line in args.get("content", "").splitlines()[:40]:
        print(f"     | {line}")
    return input("  approve? [y/N] ").strip().lower() == "y"

# ------------------------------------------------------------------- 5. LOOP
def call_model(client: OpenAI, messages: list, tools: list):
    """One model call, with a fallback model if the first one fails."""
    errors = []
    for model in filter(None, [MODEL, FALLBACK_MODEL]):
        try:
            return client.chat.completions.create(
                model=model, messages=messages, tools=tools, max_tokens=MAX_OUTPUT_TOKENS,
                extra_body={"usage": {"include": True}})  # OpenRouter reports cost
        except Exception as e:  # rate limit, no credits, model gone, ...
            errors.append(f"{model}: {e}")
            audit(event="model_error", model=model, error=str(e)[:300])
    raise RuntimeError(" | ".join(errors))


async def execute(call, mcp, workspace, approve, emit, result) -> str:
    """Run one tool call through the policy. Errors become observations."""
    name = call.function.name
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return "error: arguments were not valid JSON, try again"
    result["tool_calls"].append(name)

    decision, reason = policy(name, args)
    emit("tool_call", {"name": name, "args": args, "decision": decision})
    if decision == "ask" and not await asyncio.to_thread(approve, name, args):
        decision, reason = "deny", "the user rejected this action"
    if decision == "deny":
        audit(tool=name, args=args, decision="deny", reason=reason)
        emit("denied", reason)
        return f"DENIED: {reason}"

    try:
        if name == "run_tests":
            output = run_tests(workspace)
        elif name == "save_note":
            output = save_note(workspace, args.get("note", ""))
        else:
            res = await mcp.call_tool(name, args)
            output = "\n".join(c.text for c in res.content if hasattr(c, "text"))
    except Exception as e:
        output = f"error: {e}"
    if "is outside the workspace" in output:  # the MCP server's path jail refused it
        decision = "blocked by jail"
    audit(tool=name, args={k: str(v)[:200] for k, v in args.items()}, decision=decision, chars=len(output))
    emit("tool_result", {"name": name, "output": clip(output, 800)})
    return output


async def run_agent(task: str, workspace, config: str = "solve-with-test-loop", approve=ask_in_terminal,
                    on_event=None, jail: bool = True, client: OpenAI | None = None) -> dict:
    """Run one task to completion or until a budget runs out."""
    workspace = Path(workspace).resolve()
    emit = on_event or (lambda kind, data: None)
    if client is None:
        if not os.getenv("OPENROUTER_API_KEY"):
            raise RuntimeError("OPENROUTER_API_KEY is missing: copy .env.example to .env and add your key")
        client = OpenAI(base_url="https://openrouter.ai/api/v1",
                        api_key=os.environ["OPENROUTER_API_KEY"], max_retries=3)
    messages = [{"role": "system", "content": system_prompt(workspace)},
                {"role": "user", "content": task}]
    result = {"final": "", "stop": "", "steps": 0, "tokens": 0, "cost": 0.0,
              "tool_calls": [], "messages": messages}
    emit("user", task)

    async with mcp_session(workspace, jail) as mcp:
        tools = [as_openai_tool(t.name, t.description, t.input_schema) for t in (await mcp.list_tools()).tools]
        tools += [as_openai_tool(n, t["description"], t["parameters"]) for n, t in LOCAL_TOOLS.items()
                  if n != "run_tests" or CONFIGS[config]["run_tests"]]

        while True:
            if result["steps"] >= MAX_STEPS:
                result["stop"] = "step budget"
            elif result["tokens"] >= MAX_TOKENS:
                result["stop"] = "token budget"
            elif result["cost"] >= MAX_COST_USD:
                result["stop"] = "cost budget"
            if result["stop"]:
                emit("stopped", result["stop"])
                break

            resp = await asyncio.to_thread(call_model, client, messages, tools)
            result["steps"] += 1
            if resp.usage:
                result["tokens"] += resp.usage.total_tokens or 0
                result["cost"] += getattr(resp.usage, "cost", 0) or 0
            msg = resp.choices[0].message

            if not msg.tool_calls:  # no tool call = the agent is done
                result["final"], result["stop"] = msg.content or "", "done"
                messages.append({"role": "assistant", "content": result["final"]})
                emit("final", result["final"])
                break

            if msg.content:
                emit("thought", msg.content)
            messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in msg.tool_calls]})
            for call in msg.tool_calls:
                output = await execute(call, mcp, workspace, approve, emit, result)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": clip(output)})
            compact(messages)

    audit(event="run_end", config=config, stop=result["stop"], steps=result["steps"],
          tokens=result["tokens"], cost=result["cost"])
    return result

# -------------------------------------------------------------------- CLI
def playground(reset: bool = False) -> Path:
    """A scratch copy of demo/ so the original stays untouched."""
    pg = ROOT / "playground"
    if reset:
        shutil.rmtree(pg, ignore_errors=True)
    if not pg.exists():
        shutil.copytree(ROOT / "demo", pg)
    return pg


def print_event(kind: str, data) -> None:
    if kind == "tool_call":
        args = {k: (v if len(str(v)) < 60 else str(v)[:57] + "...") for k, v in data["args"].items()}
        print(f"  -> {data['name']}({args})  [{data['decision']}]")
    elif kind == "tool_result":
        first = data["output"].strip().splitlines()[:1]
        print(f"     {first[0][:100] if first else ''}")
    elif kind in ("denied", "stopped"):
        print(f"  xx {kind}: {data}")
    elif kind == "final":
        print(f"\nAgent: {data}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="tiny-coder: fixes small Python bugs until the tests pass.")
    ap.add_argument("task", nargs="?", default="The tests are failing. Find the bug and fix it.")
    ap.add_argument("--workspace", help="project folder (default: ./playground, a copy of ./demo)")
    ap.add_argument("--config", default="solve-with-test-loop", choices=CONFIGS)
    ap.add_argument("--reset", action="store_true", help="re-copy demo/ into playground/ first")
    ap.add_argument("--no-jail", action="store_true", help="disable the path jail (security demo only)")
    a = ap.parse_args()

    ws = Path(a.workspace) if a.workspace else playground(a.reset)
    print(f"tiny-coder | model={MODEL} | config={a.config} | workspace={ws}")
    r = asyncio.run(run_agent(a.task, ws, a.config, on_event=print_event, jail=not a.no_jail))
    print(f"\n[{r['stop']}] steps={r['steps']} tokens={r['tokens']} cost=${r['cost']:.4f}")


if __name__ == "__main__":
    main()
