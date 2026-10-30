#!/usr/bin/env python3
"""imagemagick-skill as an MCP server (stdio, JSON-RPC 2.0) - standard library only.

Every public script in ../scripts is a tool. Names, order, descriptions and inputSchema
come from the contract (scripts/_contract.py: build_contract_payload + mcp_tool), and
arguments are mapped back to each script's argv by the contract too (mcp_argv) - this
file is only the transport, so the MCP surface cannot drift from the CLI.

Both protocol eras are served ("dual-era", as the 2026-07-28 spec calls it):
  - legacy clients open with `initialize` (2024-11-05 ... 2025-11-25 are accepted);
  - modern clients send `server/discover` and/or carry the protocol version in each
    request's `_meta`; an unsupported version gets UnsupportedProtocolVersionError.

Run:
  python3 mcp/server.py                                  # stdio transport
  python3 mcp/server.py --list                           # print the tools
  python3 mcp/server.py --call probe '{"input": "/abs/photo.jpg"}'
Config (Claude Desktop / Cursor / .mcp.json):
  {"mcpServers": {"imagemagick-skill": {"command": "python3", "args": ["/abs/path/mcp/server.py"]}}}
"""
import json
import os
import signal
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)
import _contract  # noqa: E402
from _common import _group_kwargs, kill_process_tree  # noqa: E402

MODERN_VERSIONS = ("2026-07-28",)
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
SUPPORTED_VERSIONS = MODERN_VERSIONS + LEGACY_VERSIONS
META_VERSION = "io.modelcontextprotocol/protocolVersion"
DEFAULT_TIMEOUT = 600
# Over a call's own `timeout` argument: the tool stops itself at its budget (exit 124,
# code "timeout"); the server's ceiling only backs that up.
TOOL_TIMEOUT_GRACE = 30


class RpcError(Exception):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code = code
        self.data = data


_SPECS = {}


def specs():
    """Contract tools by name, in contract order (built once per process)."""
    if not _SPECS:
        for spec in _contract.build_contract_payload()["tools"]:
            _SPECS[spec["name"]] = spec
    return _SPECS


def server_info():
    return {"name": _contract.SKILL_ID, "version": _contract.VERSION}


def tool_list():
    return [_contract.mcp_tool(spec) for spec in specs().values()]


def _timeout():
    try:
        value = float(os.environ.get("IMAGEMAGICK_SKILL_MCP_TIMEOUT", DEFAULT_TIMEOUT))
    except ValueError:
        return DEFAULT_TIMEOUT
    return None if value <= 0 else value


def _run_script(cmd, ceiling):
    """Run one tool script in its own process group. Past the ceiling the script gets
    SIGTERM first - it then kills the ImageMagick process group it started - and is
    killed with its whole tree 5 s later. Returns (returncode, stdout, stderr), or
    (None, "", "") when the ceiling ran out."""
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, **_group_kwargs())
    try:
        out, err = proc.communicate(timeout=ceiling)
        return proc.returncode, out, err
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
            except Exception:
                pass
        kill_process_tree(proc)
        try:
            proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return None, "", ""


def _error_result(text, structured=None):
    result = {"content": [{"type": "text", "text": text}], "isError": True}
    if structured is not None:
        result["structuredContent"] = structured
    return result


def call_tool(name, arguments):
    spec = specs().get(name)
    if spec is None:
        raise RpcError(-32602, f"Unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise RpcError(-32602, "arguments must be an object")
    try:
        argv = _contract.mcp_argv(spec, arguments)
    except ValueError as e:
        return _error_result(str(e))
    cmd = [sys.executable, os.path.join(SCRIPTS, spec["script"])] + argv
    ceiling = _timeout()
    tool_timeout = arguments.get("timeout")
    if ceiling is not None and isinstance(tool_timeout, (int, float)) and not isinstance(tool_timeout, bool):
        ceiling = max(ceiling, float(tool_timeout) + TOOL_TIMEOUT_GRACE)
    returncode, out, err = _run_script(cmd, ceiling)
    if returncode is None:
        return _error_result(f"{name} timed out after {ceiling:g} s (IMAGEMAGICK_SKILL_MCP_TIMEOUT)")
    proc = subprocess.CompletedProcess(cmd, returncode, out, err)
    stdout = proc.stdout.strip()
    try:
        structured = json.loads(stdout)
    except ValueError:
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-12:])
        return _error_result(f"{name} did not return JSON (exit {proc.returncode})\n{tail}")
    ok = isinstance(structured, dict) and structured.get("ok") is True and proc.returncode == 0
    result = {"content": [{"type": "text", "text": stdout}], "structuredContent": structured, "isError": not ok}
    return result


def handle(request):
    """One JSON-RPC request -> result object (raises RpcError for protocol errors)."""
    method = request.get("method")
    params = request.get("params") or {}
    if not isinstance(params, dict):
        raise RpcError(-32602, "params must be an object")
    meta = params.get("_meta") or {}
    requested = meta.get(META_VERSION) if isinstance(meta, dict) else None
    modern = requested is not None
    if modern and requested not in MODERN_VERSIONS:
        raise RpcError(-32022, "Unsupported protocol version",
                       {"supported": list(SUPPORTED_VERSIONS), "requested": requested})

    if method == "initialize":
        asked = params.get("protocolVersion")
        return {
            "protocolVersion": asked if asked in LEGACY_VERSIONS else LEGACY_VERSIONS[0],
            "capabilities": {"tools": {}},
            "serverInfo": server_info(),
            "instructions": _contract.MCP_INSTRUCTIONS,
        }
    if method == "server/discover":
        result = {
            "supportedVersions": list(SUPPORTED_VERSIONS),
            "capabilities": {"tools": {}},
            "_meta": {"io.modelcontextprotocol/serverInfo": server_info()},
            "instructions": _contract.MCP_INSTRUCTIONS,
        }
    elif method == "tools/list":
        result = {"tools": tool_list()}
    elif method == "tools/call":
        result = call_tool(params.get("name", ""), params.get("arguments") or {})
    elif method == "ping":
        result = {}
    else:
        raise RpcError(-32601, f"Method not found: {method}")
    if modern or method == "server/discover":
        result = dict(result, resultType="complete")
    return result


def respond(line):
    """Handle one line of input; return the response dict, or None for a notification."""
    try:
        request = json.loads(line)
    except ValueError:
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
    if not isinstance(request, dict) or "method" not in request:
        return {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
                "error": {"code": -32600, "message": "Invalid Request"}}
    if "id" not in request:
        return None  # notification (e.g. notifications/initialized): no response
    try:
        return {"jsonrpc": "2.0", "id": request["id"], "result": handle(request)}
    except RpcError as e:
        error = {"code": e.code, "message": str(e)}
        if e.data is not None:
            error["data"] = e.data
        return {"jsonrpc": "2.0", "id": request["id"], "error": error}
    except Exception as e:  # noqa: BLE001 - a server must answer, not die
        return {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32603, "message": f"Internal error: {e}"}}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--list" in argv:
        for tool in tool_list():
            print(f"{tool['name']:10} {tool['description']}")
        return 0
    if "--call" in argv:
        i = argv.index("--call")
        name = argv[i + 1]
        arguments = json.loads(argv[i + 2]) if len(argv) > i + 2 else {}
        try:
            result = call_tool(name, arguments)
        except RpcError as e:
            print(json.dumps({"error": {"code": e.code, "message": str(e)}}, indent=2))
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if result.get("isError") else 0
    for raw in sys.stdin.buffer:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        response = respond(line)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
