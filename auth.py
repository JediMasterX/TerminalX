# auth.py

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3

import db
from passlib.context import CryptContext

router = APIRouter()
templates = Jinja2Templates(directory="templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_current_user(request: Request):
    """
    Retrieve the logged-in user from session, or None.
    """
    return request.session.get("user")


def require_auth(request: Request):
    """
    FastAPI dependency to enforce authentication.
    If no user is in session, redirect to /login.
    Otherwise return the user dict.
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return user


@router.get("/register")
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
async def register_post(request: Request,
                        username: str = Form(...),
                        password: str = Form(...)):
    conn = db.get_db()
    cursor = conn.cursor()
    # Canonicalize username to lowercase (case-insensitive policy)
    username_norm = (username or "").strip().lower()
    hashed = pwd_context.hash(password)
    # Proactively check for duplicates case-insensitively to avoid mixed-case dupes
    cursor.execute("SELECT id FROM users WHERE lower(trim(username)) = lower(trim(?))", (username_norm,))
    if cursor.fetchone():
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Username already taken"
        })
    try:
        cursor.execute(
            "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
            (username_norm, hashed)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Username already taken"
        })
    return RedirectResponse("/login", status_code=302)


@router.get("/login")
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_post(request: Request,
                     username: str = Form(...),
                     password: str = Form(...)):
    conn = db.get_db()
    cursor = conn.cursor()
    # Case-insensitive username match
    cursor.execute("SELECT * FROM users WHERE lower(trim(username)) = lower(trim(?))", ((username or "").strip(),))
    user = cursor.fetchone()
    if not user or not pwd_context.verify(password, user["hashed_password"]):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid credentials"
        })
    # Store minimal user info in session
    request.session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "is_admin": bool(user["is_admin"])
    }
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse("/login", status_code=302)
