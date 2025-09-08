import db
import os
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import Response
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
import auth, dashboard, terminal
from dashboard import get_current_user
from routers.multi_exec    import router as multi_exec_router
from routers.script_exec   import router as script_exec_router
from routers.range_gen     import router as range_gen_router
from routers.shutdown      import router as shutdown_router
from routers.file_uploader import router as file_uploader

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="CHANGE_THIS_SECRET")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

db.init_db()

# Root → Login
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/login", status_code=302)

@app.get("/config.js")
async def config_js():
    td_path = os.getenv("TD_PATH", "")
    moby_port = os.getenv("MOBY_PORT", "9090")
    
    # SFTP server configuration - keep it simple for airgapped environments
    sftp_host = os.getenv("SFTP_HOST", "")  # Empty = use current hostname
    sftp_port = os.getenv("SFTP_PORT", "3000")
    sftp_protocol = os.getenv("SFTP_PROTOCOL", "http")
    
    js_content = (
        f'window.TD_PATH = "{td_path}";\n'
        f'window.MOBY_PORT = "{moby_port}";\n'
        f'window.SFTP_HOST = "{sftp_host}";\n'
        f'window.SFTP_PORT = "{sftp_port}";\n'
        f'window.SFTP_PROTOCOL = "{sftp_protocol}";'
    )
    return Response(js_content, media_type="application/javascript")

@app.get("/api/host_status")
async def get_host_status(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    
    # Implement your host status checking logic here
    # Example: ping hosts or check last connection time
    status_data = {}
    
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, host FROM hosts WHERE user_id = ?", (user["id"],))
    hosts = cursor.fetchall()
    
    for host in hosts:
        # Simple ping check (you can make this more sophisticated)
        try:
            # Example status check - replace with your preferred method
            status_data[host["id"]] = "online"  # or "offline"
        except:
            status_data[host["id"]] = "offline"
    
    return status_data
    
    
# SSH-Portal
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(terminal.router)

# Additional tools
app.include_router(multi_exec_router)
app.include_router(script_exec_router)
app.include_router(range_gen_router)
app.include_router(shutdown_router)
app.include_router(file_uploader)
