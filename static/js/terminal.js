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

function openSftp(host, username, password) {
  const url = `http://${location.hostname}:3000/` +
              `?host=${encodeURIComponent(host)}` +
              `&username=${encodeURIComponent(username)}` +
              `&password=${encodeURIComponent(password)}`;
  window.open(
    url,
    'sftpBrowser_' + host,
    'noopener,noreferrer'
  );
}


function openTD(host) {
  const path = window.TD_PATH || "";
  const url = `http://${host}${path}`;
  window.open(url, 'tdInterface_' + host, 'noopener,noreferrer');
}

