# routers/script_exec.py
import logging, json
from pathlib import Path
import asyncssh
from fastapi import APIRouter, Request, Form, File, UploadFile, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from auth import require_auth

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/script", response_class=HTMLResponse)
def script_page(request: Request, auth=Depends(require_auth)):
    return templates.TemplateResponse("script.html", {
        "request": request,
        "default_username": "cix_user",
        "title": "ScriptExec"
    })

@router.post("/run_script")
async def run_script(
    ssh_user: str = Form(...),
    ssh_pass: str = Form(...),
    hosts: str   = Form(...),
    sudo: bool   = Form(False),
    script: UploadFile = File(...),
    auth=Depends(require_auth)
):
    hosts_list = json.loads(hosts)
    content = await script.read()
    tmp = Path("/tmp/ssh_scripts")
    tmp.mkdir(exist_ok=True)
    path = tmp / script.filename
    path.write_bytes(content)

    log = ""
    for host in hosts_list:
        logging.info(f"On {host}: uploading {script.filename}")
        async with asyncssh.connect(host,
                                   username=ssh_user,
                                   password=ssh_pass,
                                   known_hosts=None) as conn:
            async with conn.start_sftp_client() as sftp:
                await sftp.put(str(path), f"/home/{ssh_user}/{path.name}")
            cmd = f"bash /home/{ssh_user}/{path.name}"
            if sudo:
                cmd = f"echo '{ssh_pass}' | sudo -S -p '' {cmd}"
            res = await conn.run(cmd, check=False)
            log += f"[{host}] STDOUT:\n{res.stdout}\n"
            log += f"[{host}] STDERR:\n{res.stderr}\n" if res.stderr else ""
            await conn.run(f"rm /home/{ssh_user}/{path.name}")
    path.unlink()
    return log
