# terminal.py

import logging
import asyncio
import socket

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

import asyncssh
import db

# ─── Logging Setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ssh_portal.terminal")

# ─── Router & Templates ────────────────────────────────────────────────────────
router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/terminal")
async def terminal_page(request: Request, host_id: int):
    # 1) Session check
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)

    # 2) Fetch host record (and enforce permissions)
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, host FROM hosts WHERE id = ? AND (user_id = ? OR ?)",
        (host_id, user["id"], int(user["is_admin"]))
    )
    host = cursor.fetchone()
    if not host:
        return RedirectResponse("/dashboard", status_code=302)

    # 3) Build dynamic title
    title = f"Session- {host['name']} ({host['host']})"

    # 4) Render template with title & host_id
    return templates.TemplateResponse("terminal.html", {
        "request": request,
        "host_id": host_id,
        "host_name": host["name"],
        "host_addr": host["host"],
        "title": title
    })

async def safe_websocket_send(websocket: WebSocket, message: str) -> bool:
    """Safely send a message to WebSocket, return True if successful"""
    try:
        if websocket.client_state.name == "CONNECTED":
            await websocket.send_text(message)
            return True
    except Exception as e:
        logger.debug("Failed to send WebSocket message: %s", e)
    return False

@router.websocket("/ws/{host_id}")
async def websocket_terminal(websocket: WebSocket, host_id: int):
    await websocket.accept()
    logger.info("WebSocket opened for host_id=%s", host_id)

    ssh_conn = None
    proc = None

    try:
        # ── Session check ────────────────────────────────────────────────────────────
        session = websocket.scope.get("session", {})
        user = session.get("user")
        if not user:
            logger.warning("Unauthorized WS attempt")
            await safe_websocket_send(websocket, "\r\n*** ❌ Unauthorized access ***\r\n")
            await asyncio.sleep(1)  # Give time for message to be sent
            await websocket.close()
            return

        # ── Fetch host entry ─────────────────────────────────────────────────────────
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM hosts WHERE id = ? AND (user_id = ? OR ?)",
            (host_id, user["id"], int(user["is_admin"]))
        )
        host = cursor.fetchone()
        if not host:
            logger.warning("Host not found or access denied: host_id=%s user=%s", host_id, user["username"])
            await safe_websocket_send(websocket, "\r\n*** ❌ Host not found or access denied ***\r\n")
            await asyncio.sleep(1)
            await websocket.close()
            return

        # ── Send connection status ────────────────────────────────────────────────────
        await safe_websocket_send(websocket, f"\r\n🔌 Connecting to {host['username']}@{host['host']}...\r\n")

        try:
            # ── Establish SSH connection with timeout ──────────────────────────────────
            logger.info("Connecting to SSH %s@%s", host["username"], host["host"])
            
            ssh_conn = await asyncio.wait_for(
                asyncssh.connect(
                    host["host"],
                    username=host["username"],
                    password=host["password"],
                    known_hosts=None,
                    connect_timeout=10,  # 10 second connection timeout
                    keepalive_interval=30  # Keep connection alive
                ),
                timeout=15  # Overall timeout of 15 seconds
            )
            
            logger.info("SSH connection established")
            await safe_websocket_send(websocket, f"✅ Connected to {host['name']}\r\n\r\n")

            # ── Start an interactive shell process ────────────────────────────────────
            proc = await ssh_conn.create_process(term_type="xterm")
            logger.info("SSH interactive process created")

        except asyncio.TimeoutError:
            error_msg = f"\r\n*** ⏱️ Connection timeout to {host['host']} ***\r\n"
            error_msg += "*** The host might be down or unreachable ***\r\n"
            logger.warning("SSH connection timeout to %s", host["host"])
            await safe_websocket_send(websocket, error_msg)
            await asyncio.sleep(2)
            await websocket.close()
            return

        except ConnectionRefusedError:
            error_msg = f"\r\n*** ❌ Connection refused by {host['host']} ***\r\n"
            error_msg += "*** SSH service is not running or host is down ***\r\n"
            logger.warning("SSH connection refused to %s", host["host"])
            await safe_websocket_send(websocket, error_msg)
            await asyncio.sleep(2)
            await websocket.close()
            return

        except socket.gaierror as e:
            error_msg = f"\r\n*** 🌐 DNS resolution failed for {host['host']} ***\r\n"
            error_msg += f"*** {str(e)} ***\r\n"
            logger.warning("DNS resolution failed for %s: %s", host["host"], e)
            await safe_websocket_send(websocket, error_msg)
            await asyncio.sleep(2)
            await websocket.close()
            return

        except asyncssh.PermissionDenied:
            error_msg = f"\r\n*** 🔐 Authentication failed for {host['username']}@{host['host']} ***\r\n"
            error_msg += "*** Please check username and password ***\r\n"
            logger.warning("SSH authentication failed for %s@%s", host["username"], host["host"])
            await safe_websocket_send(websocket, error_msg)
            await asyncio.sleep(2)
            await websocket.close()
            return

        except asyncssh.Error as e:
            error_msg = f"\r\n*** 🔧 SSH error connecting to {host['host']} ***\r\n"
            error_msg += f"*** {str(e)} ***\r\n"
            logger.warning("SSH error connecting to %s: %s", host["host"], e)
            await safe_websocket_send(websocket, error_msg)
            await asyncio.sleep(2)
            await websocket.close()
            return

        except Exception as e:
            error_msg = f"\r\n*** ⚠️ Unexpected error connecting to {host['host']} ***\r\n"
            error_msg += f"*** {str(e)} ***\r\n"
            logger.exception("Unexpected SSH connection error to %s", host["host"])
            await safe_websocket_send(websocket, error_msg)
            await asyncio.sleep(2)
            await websocket.close()
            return

        # ── Relay data from SSH → WebSocket ──────────────────────────────────────
        async def ssh_to_ws():
            try:
                while True:
                    data = await proc.stdout.read(1024)
                    if not data:
                        logger.info("SSH process stdout EOF")
                        break
                    
                    # Only send if WebSocket is still connected
                    if not await safe_websocket_send(websocket, data):
                        logger.info("WebSocket disconnected, stopping SSH->WS relay")
                        break
                        
            except Exception as e:
                logger.debug("Error reading from SSH stdout: %s", e)
            finally:
                # Signal that SSH output ended
                await safe_websocket_send(websocket, "\r\n*** 📡 SSH session ended ***\r\n")

        # ── Relay data from WebSocket → SSH ──────────────────────────────────────
        async def ws_to_ssh():
            try:
                while True:
                    msg = await websocket.receive_text()
                    logger.debug("<- WS → SSH: %r", msg)
                    
                    if proc and not proc.stdin.is_closing():
                        proc.stdin.write(msg)
                        await proc.stdin.drain()
                    else:
                        logger.debug("SSH process stdin is closed, dropping message")
                        break
                        
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected by client")
            except Exception as e:
                logger.debug("Error in WS->SSH relay: %s", e)

        # ── Run both loops concurrently ───────────────────────────────────────────
        try:
            await asyncio.gather(
                ssh_to_ws(), 
                ws_to_ssh(), 
                return_exceptions=True
            )
        except Exception as e:
            logger.debug("Error in data relay: %s", e)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected during connection setup")
    except Exception as e:
        logger.exception("Unexpected error in WebSocket handler")
        # Try to send error message if possible
        await safe_websocket_send(websocket, f"\r\n*** ⚠️ Internal error: {str(e)} ***\r\n")

    finally:
        # ── Clean shutdown ───────────────────────────────────────────────────────
        logger.info("Cleaning up SSH connection for host_id=%s", host_id)
        
        # Close SSH process if it exists
        if proc:
            try:
                if not proc.stdin.is_closing():
                    proc.stdin.close()
                if not proc.is_closing():
                    proc.close()
                await proc.wait_closed()
            except Exception as e:
                logger.debug("Error closing SSH process: %s", e)

        # Close SSH connection if it exists
        if ssh_conn:
            try:
                if not ssh_conn.is_closing():
                    ssh_conn.close()
                await ssh_conn.wait_closed()
            except Exception as e:
                logger.debug("Error closing SSH connection: %s", e)

        # Close WebSocket if still open
        try:
            if websocket.client_state.name == "CONNECTED":
                await websocket.close()
        except Exception as e:
            logger.debug("Error closing WebSocket: %s", e)

        logger.info("SSH connection cleanup completed for host_id=%s", host_id)

@router.get("/terminal-combined")
async def combined_terminal_page(request: Request, host_id: int):
    """Combined SSH terminal and SFTP browser in split view"""
    # 1) Session check
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)

    # 2) Fetch host record (and enforce permissions)
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, host FROM hosts WHERE id = ? AND (user_id = ? OR ?)",
        (host_id, user["id"], int(user["is_admin"]))
    )
    host = cursor.fetchone()
    if not host:
        return RedirectResponse("/dashboard", status_code=302)

    # 3) Build dynamic title
    title = f"Combined Session - {host['name']} ({host['host']})"

    # 4) Render the combined template
    return templates.TemplateResponse("terminal_combined.html", {
        "request": request,
        "host_id": host_id,
        "host_name": host["name"],
        "host_addr": host["host"],
        "title": title
    })