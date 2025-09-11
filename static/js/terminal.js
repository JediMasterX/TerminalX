window.addEventListener("DOMContentLoaded", () => {
  if (typeof hostId === "undefined") return;

  const term = new Terminal({
    fontFamily: "monospace",
    theme: { background: "#000000" },
    cursorBlink: true,
    scrollback: 1000
  });

  const fitAddon = new FitAddon.FitAddon();
  const webLinksAddon = new WebLinksAddon.WebLinksAddon();
  term.loadAddon(fitAddon);
  term.loadAddon(webLinksAddon);

  const searchAddon = new SearchAddon.SearchAddon();
  const serializeAddon = new SerializeAddon.SerializeAddon();
  term.loadAddon(searchAddon);
  term.loadAddon(serializeAddon);

  const terminalContainer = document.getElementById("terminal");

  // Ensure the terminal container fills the viewport
  function adjustTerminalSize() {
    terminalContainer.style.height = window.innerHeight + "px";
    terminalContainer.style.width = window.innerWidth + "px";
    fitAddon.fit();
  }

  term.open(terminalContainer);
  adjustTerminalSize();

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/ws/${hostId}`);

  term.onData(data => socket.send(data));
  socket.onmessage = event => term.write(event.data);
  socket.onclose = () => term.write("\r\n*** Connection closed ***");

  // Resize dynamically
  window.addEventListener("resize", adjustTerminalSize);

  // In case this is inside a modal that was opened late, delay fit
  setTimeout(adjustTerminalSize, 50);
});

async function openSftp(hostOrId, username, password) {
  try {
    // Resolve SFTP target from config.js (fallbacks included)
    const proto = (window.SFTP_PROTOCOL || (location.protocol === 'https:' ? 'https' : 'http')).replace(/:$/, '');
    const hostName = (window.SFTP_HOST && window.SFTP_HOST.trim()) ? window.SFTP_HOST.trim() : location.hostname;
    const port = (window.SFTP_PORT && String(window.SFTP_PORT).trim()) ? String(window.SFTP_PORT).trim() : '3000';

    // Prefer server-side lookup by host ID to avoid exposing credentials in the DOM
    let resp;
    if (typeof hostOrId === 'number') {
      resp = await fetch('/api/sftp/mint', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host_id: hostOrId })
      });
    } else {
      // Legacy fallback: browser sends host/username/password to server (POST body)
      resp = await fetch('/api/sftp/mint', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: hostOrId, username, password })
      });
    }
    if (!resp.ok) {
      console.error('Failed to mint SFTP token', resp.status);
      return;
    }
    const data = await resp.json();
    if (!data || !data.token) {
      console.error('Invalid token response');
      return;
    }

    // Prefer placing the token in the URL hash so it never reaches server logs
    const url = `${proto}://${hostName}:${port}/#token=${encodeURIComponent(data.token)}`;
    window.open(
      url,
      'sftpBrowser_' + (typeof hostOrId === 'number' ? hostOrId : (hostOrId || '')),
      'width=1000,height=700,toolbar=no,location=no,status=no'
    );
  } catch (e) {
    console.error('openSftp error', e);
  }
}


function openTD(host) {
  const path = window.TD_PATH || "";
  const url = `http://${host}${path}`;
  window.open(url, 'tdInterface_' + host, 'noopener,noreferrer');
}

