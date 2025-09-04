from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

import db, csv
from io import StringIO

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def get_current_user(request: Request):
    return request.session.get("user")

# ── Portal Route ──────────────────────────────────────────────────────────
@router.get("/portal")
async def multiexec_portal(request: Request, hosts: str = None):
    """MultiExec portal page with optional pre-populated hosts from bulk operations"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    # Parse the hosts parameter for bulk operations
    host_list = []
    if hosts:
        try:
            host_list = [host.strip() for host in hosts.split(',') if host.strip()]
        except:
            host_list = []
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "default_username": "root",  # You can get this from user preferences
        "pre_populated_hosts": host_list
    })

# ── Updated dashboard.py with Better Nested Folder Logic ──────────────────────

@router.get("/dashboard")
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    # ─── Fetch hosts ────────────────────────────────────────────────
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hosts WHERE user_id = ?", (user["id"],))
    hosts = cursor.fetchall()

    # ─── Build nested folder tree with better logic ────────────────
    class FolderNode:
        def __init__(self):
            self.children = {}   # name → FolderNode
            self.hosts = []      # list of host-rows
            
        def to_dict(self):
            """Convert to dictionary for easier template rendering"""
            return {
                'children': {name: child.to_dict() for name, child in self.children.items()},
                'hosts': list(self.hosts)
            }

    root = FolderNode()
    
    # Process each host and build the tree
    for h in hosts:
        raw = (h["folder"] or "").strip()
        parts = [p.strip() for p in raw.split("/") if p.strip()]
        
        # If no folder specified, put in "Ungrouped"
        if not parts:
            parts = ["Ungrouped"]

        # Navigate/create the folder structure
        node = root
        for part in parts:
            if part not in node.children:
                node.children[part] = FolderNode()
            node = node.children[part]
        
        # Add host to the final folder node
        node.hosts.append(h)

    # ─── Create a flattened host list for JavaScript ───────────────
    def get_all_hosts_recursive(node, folder_path=""):
        """Recursively get all hosts with their full folder paths"""
        all_hosts = []
        
        # Add hosts from current node
        for host in node.hosts:
            host_data = dict(host)  # Convert Row to dict
            host_data['folder_path'] = folder_path if folder_path else "Ungrouped"
            all_hosts.append(host_data)
        
        # Recursively process children
        for child_name, child_node in node.children.items():
            child_path = f"{folder_path}/{child_name}" if folder_path else child_name
            all_hosts.extend(get_all_hosts_recursive(child_node, child_path))
        
        return all_hosts

    # Get flattened list for JavaScript
    all_hosts_flat = get_all_hosts_recursive(root)

    # ─── Admin user list ────────────────────────────────────────────
    users = []
    if user["is_admin"]:
        cursor.execute("SELECT id, username, is_admin FROM users")
        users = cursor.fetchall()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "folder_tree": root,
        "all_hosts_flat": all_hosts_flat,  # Add this for JavaScript
        "users": users
    })

@router.post("/add_host")
async def add_host(request: Request,
                   name: str = Form(...),
                   host: str = Form(...),
                   username: str = Form(...),
                   password: str = Form(...),
                   folder: str = Form("")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = db.get_db()
    cursor = conn.cursor()
    # Defensive: prevent duplicate hosts per user (case/whitespace insensitive)
    norm_host = (host or "").strip()
    cursor.execute(
        "SELECT 1 FROM hosts WHERE user_id = ? AND lower(trim(host)) = lower(trim(?))",
        (user["id"], norm_host)
    )
    exists = cursor.fetchone()
    if exists:
        # Skip inserting duplicate and just return to dashboard
        return RedirectResponse("/dashboard", status_code=302)

    cursor.execute(
        "INSERT INTO hosts (user_id, name, host, username, password, folder) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user["id"], name, norm_host, username, password, folder.strip())
    )
    conn.commit()
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/edit_host")
async def edit_host_get(request: Request, host_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hosts WHERE id = ?", (host_id,))
    host = cursor.fetchone()
    if not host or (host["user_id"] != user["id"] and not user["is_admin"]):
        return RedirectResponse("/dashboard", status_code=302)

    return templates.TemplateResponse("edit_host.html", {
        "request": request,
        "host": host
    })


@router.post("/edit_host")
async def edit_host_post(request: Request,
                         host_id: int = Form(...),
                         name: str = Form(...),
                         host: str = Form(...),
                         username: str = Form(...),
                         password: str = Form(...),
                         folder: str = Form("")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM hosts WHERE id = ?", (host_id,))
    row = cursor.fetchone()
    if not row or (row["user_id"] != user["id"] and not user["is_admin"]):
        return RedirectResponse("/dashboard", status_code=302)

    cursor.execute("""
        UPDATE hosts
           SET name     = ?,
               host     = ?,
               username = ?,
               password = ?,
               folder   = ?
         WHERE id       = ?
    """, (name, host, username, password, folder.strip(), host_id))
    conn.commit()
    return RedirectResponse("/dashboard", status_code=302)


@router.post("/delete_host")
async def delete_host(request: Request, host_id: int = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM hosts WHERE id = ?", (host_id,))
    row = cursor.fetchone()
    if not row or (row["user_id"] != user["id"] and not user["is_admin"]):
        return RedirectResponse("/dashboard", status_code=302)

    cursor.execute("DELETE FROM hosts WHERE id = ?", (host_id,))
    conn.commit()
    return RedirectResponse("/dashboard", status_code=302)


@router.post("/delete_user")
async def delete_user(request: Request, user_id: int = Form(...)):
    user = get_current_user(request)
    if not user or not user["is_admin"]:
        return RedirectResponse("/login", status_code=302)

    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/export_hosts")
async def export_hosts(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, host, username, password, folder "
        "FROM hosts WHERE user_id = ?",
        (user["id"],)
    )
    rows = cursor.fetchall()

    def iter_csv():
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(["name", "host", "username", "password", "folder"])
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)
        for r in rows:
            writer.writerow([r["name"], r["host"], r["username"], r["password"], r["folder"]])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    headers = {
        "Content-Disposition": f"attachment; filename=hosts_{user['username']}.csv"
    }
    return StreamingResponse(iter_csv(), media_type="text/csv", headers=headers)


@router.get("/import_hosts")
async def import_hosts_get(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("import_hosts.html", {"request": request})



@router.post("/import_hosts")
async def import_hosts_post(request: Request, file: UploadFile = File(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    content = (await file.read()).decode()
    reader = csv.DictReader(StringIO(content))
    conn = db.get_db()
    cursor = conn.cursor()
    # Preload existing hosts for this user for fast duplicate checking
    cursor.execute("SELECT lower(trim(host)) AS h FROM hosts WHERE user_id = ?", (user["id"],))
    existing = {row["h"] for row in cursor.fetchall() if row["h"] is not None}
    inserted = 0
    skipped = 0
    for row in reader:
        name_v = (row.get("name", "") or "").strip()
        host_v = (row.get("host", "") or "").strip()
        username_v = (row.get("username", "") or "").strip()
        password_v = (row.get("password", "") or "").strip()
        folder_v = (row.get("folder", "") or "").strip()

        # Skip blank host rows
        if not host_v:
            skipped += 1
            continue

        key = host_v.lower()
        if key in existing:
            skipped += 1
            continue

        cursor.execute(
            "INSERT INTO hosts (user_id, name, host, username, password, folder) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                user["id"],
                name_v,
                host_v,
                username_v,
                password_v,
                folder_v
            )
        )
        existing.add(key)
        inserted += 1
    conn.commit()
    return RedirectResponse("/dashboard", status_code=302)
