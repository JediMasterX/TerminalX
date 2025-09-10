"""Multi-host command execution with staged, streaming updates.

Streams per-host stages and output over WebSocket:
 - connecting -> connected -> command_started -> completed (with exit status)
Aggregates a final summary and enforces bounded concurrency so it can scale
to 30+ hosts without overwhelming the server/UI.
"""

import asyncio
import logging
import os
import asyncssh
import json
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from auth import require_auth


router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger("ssh_portal.multi_exec")


def _ensure_exit_code(val):
    try:
        if isinstance(val, int):
            return val
        code = getattr(val, "exit_status", None)
        if code is None:
            code = getattr(val, "returncode", None)
        if isinstance(code, int):
            return code
        if isinstance(val, str):
            import re
            m = re.search(r"exit_status:\s*(\d+)", val) or re.search(r"returncode:\s*(\d+)", val)
            if m:
                return int(m.group(1))
        if isinstance(code, str) and code.isdigit():
            return int(code)
    except Exception:
        pass
    return None


@router.get("/portal", response_class=HTMLResponse)
def portal(request: Request, auth=Depends(require_auth)):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "default_username": "cix_user", "title": "MultiExec"},
    )


def _sanitize(obj):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize(v) for v in obj]
    # Fallback: stringify unknown objects (e.g., SSHCompletedProcess)
    try:
        return str(obj)
    except Exception:
        return repr(obj)


async def _safe_ws_send(ws: WebSocket, payload: dict) -> bool:
    try:
        data = _sanitize(payload)
        await ws.send_text(json.dumps(data, ensure_ascii=False))
        return True
    except Exception as e:
        try:
            ptype = payload.get("type") if isinstance(payload, dict) else None
        except Exception:
            ptype = None
        logger.warning("WS send failed for type=%s: %s", ptype, e)
        return False


def _parse_hosts(data: dict) -> list[str]:
    hosts: list[str] = []
    file_hosts = data.get("hosts_file_lines", [])
    if file_hosts:
        hosts = [h.strip() for h in file_hosts if h and h.strip()]
    else:
        rng = (data.get("host_range") or "").strip()
        if not rng:
            return []
        if "-" in rng and "." in rng:
            try:
                base, suffix = rng.rsplit(".", 1)
                s, e = map(int, suffix.split("-"))
                hosts = [f"{base}.{i}" for i in range(s, e + 1)]
            except Exception:
                hosts = [rng]
        else:
            hosts = [rng]
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for h in hosts:
        if h not in seen:
            unique.append(h)
            seen.add(h)
    return unique


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()

    # Each websocket session is single-execution to keep state simple
    try:
        data = await ws.receive_json()
    except Exception:
        await ws.close(code=1003)
        return

    # AuthN check via session
    session_user = ws.scope.get("session", {}).get("user")
    if not session_user:
        await ws.close(code=1008)
        return

    ssh_user = data.get("ssh_user", "")
    ssh_pass = data.get("ssh_pass", "")
    command = (data.get("command") or "").strip()
    hosts = _parse_hosts(data)

    if not hosts or not command or not ssh_user:
        await _safe_ws_send(ws, {"type": "error", "message": "Missing hosts, command or username"})
        await ws.close()
        return

    logger.info("Launching `%s` on %d host(s)", command, len(hosts))

    # Concurrency bound (tunable via env)
    try:
        limit = int(os.getenv("MULTI_EXEC_CONCURRENCY", "12"))
    except ValueError:
        limit = 12
    sem = asyncio.Semaphore(max(1, limit))
    ws_lock = asyncio.Lock()

    # Shared counters
    success = 0
    failed = 0
    started_hosts = 0
    start_ts = asyncio.get_event_loop().time()
    host_results: dict[str, dict] = {}

    async def send(payload: dict):
        async with ws_lock:
            await _safe_ws_send(ws, payload)

    async def stream_process(host: str, conn: asyncssh.SSHClientConnection) -> tuple[bool, int | None]:
        # Start process and stream output; return (ok, exit_status)
        await send({"type": "host_status", "host": host, "stage": "command_starting"})
        proc = None
        exit_status: int | None = None
        # 1) Start process (failures here imply failure)
        try:
            try:
                import shlex
                shell_cmd = f"bash -lc {shlex.quote(command)}"
            except Exception:
                shell_cmd = command
            proc = await conn.create_process(shell_cmd, encoding="utf-8", errors="replace")
        except Exception:
            return (False, None)

        await send({"type": "host_status", "host": host, "stage": "command_started"})

        # 2) Stream output (any reader error should NOT flip success if exit_status==0)
        out_buf: list[str] = []
        err_buf: list[str] = []
        FLUSH_LINES = 20

        async def flush():
            if out_buf:
                chunk = "".join(out_buf)
                out_buf.clear()
                await send({"type": "output", "host": host, "stream": "stdout", "data": chunk})
            if err_buf:
                chunk = "".join(err_buf)
                err_buf.clear()
                if chunk.strip():
                    await send({"type": "output", "host": host, "stream": "stderr", "data": chunk})

        async def read_stream(reader, target_buf):
            try:
                async for line in reader:
                    if isinstance(line, bytes):
                        try:
                            line = line.decode("utf-8", "replace")
                        except Exception:
                            line = line.decode(errors="replace")
                    target_buf.append(line)
                    if len(target_buf) >= FLUSH_LINES:
                        await flush()
            except Exception as e:
                # Log to UI but don't change outcome
                await send({"type": "output", "host": host, "stream": "stderr", "data": f"[reader-error] {e}\n"})

        read_out = asyncio.create_task(read_stream(proc.stdout, out_buf))
        read_err = asyncio.create_task(read_stream(proc.stderr, err_buf))

        # Get exit status as early as possible and report completion before draining
        exit_status = await proc.wait()
        ex = _ensure_exit_code(exit_status)
        ok_now = (ex == 0 if ex is not None else False)
        # Emit early completion notification to reduce risk of client missing it
        await send({
            "type": "host_status",
            "host": host,
            "stage": "completed",
            "ok": ok_now,
            "exit_status": ex,
        })

        await asyncio.gather(read_out, read_err, return_exceptions=True)
        await flush()

        return (ok_now, exit_status)

    async def run_host(host: str):
        nonlocal started_hosts, success, failed
        async with sem:
            await send({"type": "host_status", "host": host, "stage": "connecting"})
            try:
                conn = await asyncssh.connect(
                    host, username=ssh_user, password=ssh_pass, known_hosts=None
                )
            except Exception as e:
                failed += 1
                await send({"type": "host_status", "host": host, "stage": "connect_failed", "error": str(e)})
                return
            await send({"type": "host_status", "host": host, "stage": "connected"})
            started_hosts += 1
            ok, exit_status = await stream_process(host, conn)
            ex = _ensure_exit_code(exit_status)
            if ex is not None:
                ok = (ex == 0)
            if ok:
                success += 1
            else:
                failed += 1
            result_evt = {
                "type": "host_status",
                "host": host,
                "stage": "completed",
                "ok": ok,
                "exit_status": ex,
            }
            host_results[host] = {"ok": ok, "exit_status": ex}
            await send(result_evt)
            try:
                conn.close()
            except Exception:
                pass

    # Kick off all host tasks
    tasks = [asyncio.create_task(run_host(h)) for h in hosts]
    await send({"type": "init", "total_hosts": len(hosts)})

    try:
        await asyncio.gather(*tasks)
    except WebSocketDisconnect:
        for t in tasks:
            t.cancel()
    finally:
        duration = asyncio.get_event_loop().time() - start_ts
        await send({
            "type": "summary",
            "total_hosts": len(hosts),
            "started": started_hosts,
            "success": success,
            "failure": failed,
            "duration_sec": round(duration, 2),
            "results": host_results,
        })
        # Emit a final 'done' signal and small delay to let client process frames
        await send({
            "type": "done",
            "results": host_results,
            "success": success,
            "failure": failed,
        })
        # Give client time to receive 'done' and close from its side.
        try:
            await asyncio.wait_for(ws.receive_text(), timeout=2.0)
        except Exception:
            # Client may have already closed or not send anything; leave socket to be closed by client.
            try:
                await asyncio.sleep(0.2)
            except Exception:
                pass
