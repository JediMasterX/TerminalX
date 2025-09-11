# TerminalX

Modern, Dockerized SSH operations dashboard for teams. TerminalX provides a fast web UI to search and manage hosts, open interactive terminals, execute commands across many machines, run scripts, move files, and more — all from your browser.

## Features
- Interactive terminals: Open a popup or slide‑in overlay terminal per host (xterm.js powered)
- Multi‑host exec: Send a single command to many hosts and view aggregated output
- Script execution: Upload and run scripts across selected hosts with live output
- File uploader: Distribute files/directories to multiple hosts with progress
- Tree/Folder view: Organize hosts in nested folders; search, pin, and bulk‑select
- Right‑click copy/paste: Custom context menu in terminals for Copy and Paste
- Web links + search in terminal: xterm addons for URLs and find-in-terminal
- Secure auth: Session‑based login with optional admin role
- SFTP launcher: One‑click SFTP browser launch via short‑lived token
- Simple deploy: Single container via Docker Compose

## Tech Stack
- Backend: Python (FastAPI/Starlette), WebSockets
- Frontend: Vanilla JS, xterm.js (fit, web-links, search, serialize addons)
- Templates/Styles: Jinja2, CSS
- DB/Storage: SQLite (app.db)
- Container: Docker / Docker Compose

## Quick Start
1) Build the Docker image
   - `docker build -t terminalx:1.1.3.2 .` (or use the provided compose file)

2) Start with Docker Compose
   - `docker compose up -d`

3) Open the app
   - Visit `http://localhost:8087` and sign in

Default ports and service name are defined in `docker-compose.yml`.

## Configuration
Environment variables can be supplied via compose or environment.

- `TOKEN_SECRET`: Secret used for token and session encryption
- `SFTP_PROTOCOL`, `SFTP_HOST`, `SFTP_PORT`: Configure SFTP helper integration
- `TD_PATH`: Optional path for the TD integration link

You can also adjust the container name, ports, and volumes in `docker-compose.yml`.

## Key Workflows
- Open a terminal
  - From Dashboard: click ⚡ (quick popup) or 💻 (full overlay)
  - Right‑click inside terminal to Copy/Paste; Ctrl/Cmd shortcuts work too

- Run a command on many hosts
  - Select hosts → Bulk Actions → MultiExec (or open the MultiExec page)

- Execute a script
  - Go to ScriptExec, upload or paste a script, choose target hosts, run and monitor output

- Upload files
  - Open FileUploader, select files/targets, track delivery status in the terminal-style output

- Manage hosts
  - Use the tree view to organize, search, pin, select, and perform bulk actions

## Security Notes
- Clipboard paste requires browser permission (HTTPS or localhost recommended). If blocked, use Ctrl/Cmd+V.
- Sensitive query params and tokens are removed from the URL bar client‑side.
- SFTP launches use short‑lived tokens minted by the server.

## Project Layout (high level)
- `main.py`: App entry and router registration
- `dashboard.py`, `terminal.py`: UI and WebSocket terminal endpoints
- `templates/`: Jinja2 HTML templates (dashboard, terminal, etc.)
- `static/js/`: Frontend logic (treeview, terminals, multi/script exec, uploader)
- `static/css/style.css`: Global styles and terminal context‑menu styles
- `app.db`: SQLite database
- `docker-compose.yml`, `dockerfile`: Containerization

## Troubleshooting
- “openPopup is not defined”: Hard refresh the browser to clear cached JS
- Clipboard paste not working: Ensure HTTPS or allow clipboard permissions
- Terminal not resizing: Resize the window once; fit addon recalculates on resize

## License
Internal/preview project. Do not distribute without permission.
