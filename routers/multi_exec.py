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
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from auth import require_auth


router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger("ssh_portal.multi_exec")


@router.get("/portal", response_class=HTMLResponse)
def portal(request: Request, auth=Depends(require_auth)):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "default_username": "cix_user", "title": "MultiExec"},
    )


async def _safe_ws_send(ws: WebSocket, payload: dict) -> bool:
    try:
        await ws.send_json(payload)
        return True
    except Exception as e:
        logger.debug("WS send failed: %s", e)
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

    async def send(payload: dict):
        async with ws_lock:
            await _safe_ws_send(ws, payload)

    async def stream_process(host: str, conn: asyncssh.SSHClientConnection):
        nonlocal success, failed
        # Start process and stream output
        await send({"type": "host_status", "host": host, "stage": "command_starting"})
        try:
            # Ensure text mode and proper shell semantics (support &&, ||, env, globs)
            try:
                import shlex
                shell_cmd = f"bash -lc {shlex.quote(command)}"
            except Exception:
                shell_cmd = command
            proc = await conn.create_process(shell_cmd, encoding="utf-8", errors="replace")
            await send({"type": "host_status", "host": host, "stage": "command_started"})

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
                    # Avoid sending empty/whitespace-only stderr chunks which create misleading ERR> lines
                    if chunk.strip():
                        await send({"type": "output", "host": host, "stream": "stderr", "data": chunk})

            async def read_stream(reader, target_buf):
                try:
                    async for line in reader:
                        # reader yields str when encoding is set; guard just in case
                        if isinstance(line, bytes):
                            try:
                                line = line.decode("utf-8", "replace")
                            except Exception:
                                line = line.decode(errors="replace")
                        target_buf.append(line)
                        if len(target_buf) >= FLUSH_LINES:
                            await flush()
                except Exception as e:
                    await send({"type": "output", "host": host, "stream": "stderr", "data": f"[reader-error] {e}\n"})

            # Consume both streams concurrently
            read_out = asyncio.create_task(read_stream(proc.stdout, out_buf))
            read_err = asyncio.create_task(read_stream(proc.stderr, err_buf))

            # Wait for process to exit and readers to drain
            exit_status = await proc.wait()
            await asyncio.gather(read_out, read_err, return_exceptions=True)
            await flush()

            ok = (exit_status == 0)
            if ok:
                success += 1
            else:
                failed += 1
            await send({
                "type": "host_status",
                "host": host,
                "stage": "completed",
                "ok": ok,
                "exit_status": exit_status,
            })
        except Exception as e:
            failed += 1
            await send({
                "type": "host_status",
                "host": host,
                "stage": "error",
                "error": str(e),
            })

    async def run_host(host: str):
        nonlocal started_hosts
        async with sem:
            await send({"type": "host_status", "host": host, "stage": "connecting"})
            try:
                conn = await asyncssh.connect(
                    host, username=ssh_user, password=ssh_pass, known_hosts=None
                )
            except Exception as e:
                await send({"type": "host_status", "host": host, "stage": "connect_failed", "error": str(e)})
                return
            await send({"type": "host_status", "host": host, "stage": "connected"})
            started_hosts += 1
            await stream_process(host, conn)
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
        await send(
            {
                "type": "summary",
                "total_hosts": len(hosts),
                "started": started_hosts,
                "success": success,
                "failure": failed,
                "duration_sec": round(duration, 2),
            }
        )
        await ws.close()
