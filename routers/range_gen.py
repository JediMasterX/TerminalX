# routers/range_gen.py
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from auth import require_auth

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/range", response_class=HTMLResponse)
def range_page(request: Request, auth=Depends(require_auth)):
    return templates.TemplateResponse("range.html", {
        "request": request,
        "title": "RangeGen"
    })
