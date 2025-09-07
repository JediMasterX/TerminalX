# routers/shutdown.py

import os
import signal
import asyncio

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from auth import require_auth

router = APIRouter()

@router.api_route("/shutdown", methods=["GET", "POST"])
async def shutdown(request: Request, user=Depends(require_auth)):
    # Only admins can shut down
    if not user.get("is_admin"):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    # Schedule a forceful kill of this entire process group
    def kill_all():
        pgid = os.getpgid(os.getpid())
        # SIGKILL to prevent any cleanup or respawns
        os.killpg(pgid, signal.SIGKILL)

    # Delay just enough to allow the JSONResponse to be sent
    asyncio.get_event_loop().call_later(0.1, kill_all)

    return JSONResponse({"detail": "Shutting down immediately"}, status_code=200)
