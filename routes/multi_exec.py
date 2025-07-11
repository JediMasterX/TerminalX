# routers/multi_exec.py
import asyncio, logging, json
import asyncssh
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from auth import require_auth

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/portal", response_class=HTMLResponse)
def portal(request: Request, auth=Depends(require_auth)):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "default_username": "cix_user",
        "title": "MultiExec"
    })

@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    data = await ws.receive_json()
    # ... same host-list parsing as before :contentReference[oaicite:12]{index=12}:contentReference[oaicite:13]{index=13} ...
    hosts = []
    file_hosts = data.get("hosts_file_lines", [])
    if file_hosts:
        hosts = [h for h in file_hosts if h.strip()]
    else:
        rng = data.get("host_range", "").strip()
        if "-" in rng and "." in rng:
            base, suffix = rng.rsplit(".", 1)
            s,e = map(int, suffix.split("-"))
            hosts = [f"{base}.{i}" for i in range(s, e+1)]
        else:
            hosts = [rng]
    user = ws.scope.get("session", {}).get("user")
    if not user:
        # no session → close immediately
        await ws.close(code=1008)
        return
    user, pw, cmd = data["ssh_user"], data["ssh_pass"], data["command"]
    logging.info(f"Launching `{cmd}` on {hosts}")

    async def run_host(host):
        try:
            async with asyncssh.connect(host, username=user, password=pw, known_hosts=None) as conn:
                res = await conn.run(cmd, check=False)
                await ws.send_json({"host": host, "output": res.stdout})
                if res.stderr:
                    await ws.send_json({"host": host, "output": f"ERR> {res.stderr}"})
        except Exception as e:
            await ws.send_json({"host": host, "output": f"ERROR: {e}"})

    tasks = [asyncio.create_task(run_host(h)) for h in hosts]
    try:
        await asyncio.wait(tasks)
    except WebSocketDisconnect:
        for t in tasks: t.cancel()
    finally:
        await ws.close()
