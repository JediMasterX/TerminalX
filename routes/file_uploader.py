from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from auth import require_auth
import json, asyncssh
from pathlib import Path
import logging
import asyncio

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request, auth=Depends(require_auth)):
    return templates.TemplateResponse("file_uploader.html", {
        "request": request,
        "default_username": "root",
        "title": "FileUploader"
    })

@router.post("/upload_file")
async def upload_file(
    ssh_user: str = Form(...),
    ssh_pass: str = Form(...),
    hosts: str = Form(...),
    remote_path: str = Form("/tmp/uploads"),
    file: UploadFile = File(...),
    auth=Depends(require_auth)
):
    hosts_list = json.loads(hosts)
    content = await file.read()
    local_tmp = Path("/tmp/uploads")
    local_tmp.mkdir(exist_ok=True)
    path = local_tmp / file.filename
    path.write_bytes(content)

    logger.info("🚀 Upload initiated")

    async def event_stream():
        yield "data: 🚀 Upload log started\n\n"

        for host in hosts_list:
            try:
                msg = f"[{host}] Connecting..."
                logger.info(msg)
                yield f"data: {msg}\n\n"

                async with asyncssh.connect(host, username=ssh_user, password=ssh_pass, known_hosts=None) as conn:
                    clean_path = remote_path.rstrip("/")
                    mkdir_cmd = f"mkdir -p {clean_path}"
                    result = await conn.run(mkdir_cmd, check=False)
                    if result.exit_status == 0:
                        msg = f"[{host}] 📁 Ensured directory {clean_path} exists"
                        logger.info(msg)
                        yield f"data: {msg}\n\n"
                    else:
                        msg = f"[{host}] ⚠ Failed to mkdir: {result.stderr}"
                        logger.warning(msg)
                        yield f"data: {msg}\n\n"

                    async with conn.start_sftp_client() as sftp:
                        remote_full = f"{clean_path}/{file.filename}"
                        await sftp.put(str(path), remote_full)
                        msg = f"[{host}] ✅ Uploaded to {remote_full}"
                        logger.info(msg)
                        yield f"data: {msg}\n\n"

            except Exception as e:
                msg = f"[{host}] ❌ Upload failed: {e}"
                logger.error(msg)
                yield f"data: {msg}\n\n"

            await asyncio.sleep(0.05)  # small delay for smoother streaming

        msg = " 🧭 Upload finished - look for errors if they occured"
        logger.info(msg)
        yield f"data: {msg}\n\n"
        path.unlink()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
