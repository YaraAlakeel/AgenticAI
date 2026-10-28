"""MCP server: the agent's file tools, served over stdio.

Why a separate process? The sandbox (the path jail) lives here, at the
server boundary. Whatever the model asks for, this process can only touch
files inside the workspace folder. The harness (agent.py) never touches
files directly, so it cannot get the jail wrong.

Run by agent.py as:  python workspace_server.py <workspace_dir>
Set WORKSPACE_JAIL=off to disable the jail (only for the security demo).
"""

import os
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError  # message reaches the model

WORKSPACE = Path(sys.argv[1]).resolve()
JAIL_ON = os.environ.get("WORKSPACE_JAIL", "on") != "off" # It locks a program to one folder of the file system
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git"}

server = MCPServer("workspace") # creates a empty server named workspace


def resolve(path: str) -> Path:
    """THE DEFENCE: refuse any path that resolves outside the workspace."""
    p = (WORKSPACE / path).resolve()
    if JAIL_ON and not p.is_relative_to(WORKSPACE):
        raise ToolError(f"DENIED: '{path}' is outside the workspace")
    return p


@server.tool()
def list_files() -> str:
    """List every file in the project, one relative path per line."""
    files = [
        p.relative_to(WORKSPACE).as_posix()
        for p in sorted(WORKSPACE.rglob("*"))
        if p.is_file() and not SKIP_DIRS & set(p.parts)
    ]
    return "\n".join(files) or "(empty project)"


@server.tool()
def read_file(path: str) -> str:
    """Read a text file. `path` is relative to the project root."""
    p = resolve(path)
    if not p.is_file():
        raise ToolError(f"no such file: {path} (call list_files)")
    return p.read_text(encoding="utf-8-sig")


@server.tool()
def write_file(path: str, content: str) -> str:
    """Create or overwrite a text file with the FULL new content."""
    p = resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {path}"


if __name__ == "__main__":
    server.run("stdio") # starts the server and makes it communicate over stdin/stdout with the harness (agent.py), which the agent can request to call the tools above, and the server will respond with the result or error message.
