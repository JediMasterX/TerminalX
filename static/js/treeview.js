document.addEventListener("DOMContentLoaded", () => {
  // Treeview toggles
  const togglers = document.getElementsByClassName("caret");
  for (let t of togglers) {
    t.addEventListener("click", function () {
      this.parentElement.querySelector(".nested").classList.toggle("active");
      this.classList.toggle("caret-down");
    });
  }

  // Close terminal button
  const closeBtn = document.getElementById("close-terminal");
  if (closeBtn) {
    closeBtn.addEventListener("click", closeTerminalOverlay);
  }
});

// For new moby and surf buttons
function openWeb(ip) {
  const url = `http://${ip}`;
  window.open(url, "_blank");
}

function openPort9090(ip) {
  const port = window.MOBY_PORT || "9090";
  const url = `http://${ip}:${port}`;
  window.open(url, "_blank");
}

// For terminal popup - creates a clean popup window with just the terminal
function openPopup(hostId, hostName, hostAddress) {
  // Create a clean popup window with minimal content
  const popup = window.open(
    '',
    "popupTerminal" + hostId,
    "width=900,height=600,menubar=no,toolbar=no,location=no,status=no,scrollbars=no,resizable=yes"
  );

  const title = `Terminal - ${hostName} (${hostAddress})`;
  popup.document.title = title;

  // Write minimal HTML structure to the popup - styles now in CSS
  popup.document.write(`
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>${title}</title>
      <link rel="stylesheet" href="/static/vendor/xterm/xterm.css">
      <link rel="stylesheet" href="/static/css/style.css">
      <style>
        * {
          margin: 0;
          padding: 0;
          box-sizing: border-box;
        }
        
        body {
          background: #000;
          color: #fff;
          font-family: monospace;
          overflow: hidden;
          height: 100vh;
          display: flex;
          flex-direction: column;
        }
        
        .terminal-header {
          background: #1a1a1a;
          padding: 8px 12px;
          border-bottom: 1px solid #333;
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 12px;
          color: #ccc;
          flex-shrink: 0;
        }
        
        .terminal-title {
          font-weight: bold;
        }
        
        .terminal-close {
          background: #ff4444;
          color: white;
          border: none;
          border-radius: 3px;
          padding: 4px 8px;
          cursor: pointer;
          font-size: 11px;
        }
        
        .terminal-close:hover {
          background: #ff6666;
        }
        
        #terminal {
          flex: 1;
          width: 100%;
          background: #000;
        }
        
        .xterm-viewport {
          background: #000 !important;
        }
        
        .connection-status {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          text-align: center;
          color: #ccc;
          font-family: monospace;
          z-index: 1000;
          background: rgba(0, 0, 0, 0.8);
          padding: 20px;
          border-radius: 8px;
          border: 1px solid #333;
        }
        
        .spinner {
          border: 2px solid #333;
          border-top: 2px solid #fff;
          border-radius: 50%;
          width: 30px;
          height: 30px;
          animation: spin 1s linear infinite;
          margin: 0 auto 10px;
        }
        
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }

        /* Context menu styles */
        .terminal-context-menu {
          position: fixed;
          background: #1f2937;
          color: #e5e7eb;
          border: 1px solid #374151;
          border-radius: 6px;
          min-width: 160px;
          box-shadow: 0 10px 20px rgba(0,0,0,0.35);
          padding: 6px 0;
          z-index: 99999;
          display: none;
        }
        .terminal-context-menu .item {
          padding: 8px 14px;
          cursor: pointer;
          font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, sans-serif;
          font-size: 13px;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .terminal-context-menu .item:hover { background: #374151; }
        .terminal-context-menu .item.disabled { opacity: 0.5; cursor: not-allowed; }
        .terminal-context-menu .separator { height: 1px; background: #2d3748; margin: 6px 0; }
      </style>
    </head>
    <body>
      <div class="terminal-header">
        <span class="terminal-title">${hostName} (${hostAddress})</span>
        <button class="terminal-close" onclick="window.close()">×</button>
      </div>
      <div id="terminal"></div>
      <div id="connectionStatus" class="connection-status" style="display: none;">
        <div class="spinner"></div>
        <div>Connecting to ${hostName}...</div>
      </div>
      
      <script src="/static/vendor/xterm/xterm.js"></script>
      <script src="/static/vendor/xterm/xterm-addon-fit.js"></script>
      <script src="/static/vendor/xterm/xterm-addon-web-links.js"></script>
      
      <script>
        const hostId = ${hostId};
        let term, socket, fitAddon;
        let isConnected = false;
        
        function showConnectionStatus(show) {
          const status = document.getElementById('connectionStatus');
          if (status) {
            status.style.display = show ? 'block' : 'none';
          }
        }
        
        function initTerminal() {
          term = new Terminal({
            fontFamily: 'Menlo, Monaco, "Courier New", monospace',
            fontSize: 14,
            theme: { 
              background: '#000000',
              foreground: '#ffffff',
              cursor: '#ffffff'
            },
            cursorBlink: true,
            scrollback: 1000,
            allowTransparency: false
          });

          fitAddon = new FitAddon.FitAddon();
          const webLinksAddon = new WebLinksAddon.WebLinksAddon();
          
          term.loadAddon(fitAddon);
          term.loadAddon(webLinksAddon);
          
          const terminalElement = document.getElementById('terminal');
          term.open(terminalElement);

          // Fit terminal to container
          fitTerminal();

          // Attach context menu for copy/paste
          attachTerminalContextMenu(term, terminalElement);
          
          // Show connection status
          showConnectionStatus(true);
          
          // Connect WebSocket
          const protocol = location.protocol === "https:" ? "wss" : "ws";
          const wsUrl = protocol + "://" + location.host + "/ws/" + hostId;
          
          socket = new WebSocket(wsUrl);
          
          socket.onopen = () => {
            console.log("Terminal WebSocket connected");
            showConnectionStatus(false);
            isConnected = true;
          };
          
          socket.onerror = (err) => {
            console.error("WebSocket error:", err);
            showConnectionStatus(false);
            if (!isConnected) {
              term.write("\\r\\n*** ❌ WebSocket connection failed ***\\r\\n");
              term.write("*** Please check your network connection ***\\r\\n");
            }
          };
          
          socket.onclose = (event) => {
            console.log("Terminal WebSocket disconnected", event.code, event.reason);
            showConnectionStatus(false);
            if (isConnected) {
              term.write("\\r\\n*** 📡 Connection closed ***\\r\\n");
            }
            isConnected = false;
          };
          
          socket.onmessage = event => {
            term.write(event.data);
            if (!isConnected) {
              showConnectionStatus(false);
              isConnected = true;
            }
          };
          
          term.onData(data => {
            if (socket.readyState === WebSocket.OPEN) {
              socket.send(data);
            }
          });
          
          // Handle window resize
          window.addEventListener('resize', fitTerminal);
          
          // Connection timeout
          setTimeout(() => {
            if (!isConnected) {
              showConnectionStatus(false);
              term.write("\\r\\n*** ⏱️ Connection timeout ***\\r\\n");
              term.write("*** The host might be unreachable ***\\r\\n");
            }
          }, 30000); // 30 second timeout
          
          // Cleanup on window close
          window.addEventListener('beforeunload', () => {
            if (socket) socket.close();
            if (term) term.dispose();
          });
        }
        
        function fitTerminal() {
          if (fitAddon && term) {
            setTimeout(() => {
              fitAddon.fit();
            }, 10);
          }
        }
        
        // Initialize when DOM is ready
        if (document.readyState === 'loading') {
          document.addEventListener('DOMContentLoaded', initTerminal);
        } else {
          initTerminal();
        }

        function attachTerminalContextMenu(term, container) {
          const menu = document.createElement('div');
          menu.className = 'terminal-context-menu';
          menu.innerHTML = '<div class="item" data-action="copy">📋 Copy<\/div>' +
                           '<div class="item" data-action="paste">📥 Paste<\/div>';
          document.body.appendChild(menu);

          function hideMenu() { menu.style.display = 'none'; }
          function showMenu(x, y) {
            // Enable/disable copy based on selection
            const copyItem = menu.querySelector('[data-action="copy"]');
            if (term.hasSelection && term.hasSelection()) copyItem.classList.remove('disabled');
            else copyItem.classList.add('disabled');

            // Position within viewport
            const vw = window.innerWidth, vh = window.innerHeight;
            const rect = { w: menu.offsetWidth || 180, h: menu.offsetHeight || 80 };
            const left = Math.min(x, vw - rect.w - 8);
            const top = Math.min(y, vh - rect.h - 8);
            menu.style.left = left + 'px';
            menu.style.top = top + 'px';
            menu.style.display = 'block';
          }

          container.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            hideMenu();
            showMenu(e.clientX, e.clientY);
          });

          document.addEventListener('click', (e) => {
            if (!menu.contains(e.target)) hideMenu();
          });
          document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideMenu(); });
          container.addEventListener('wheel', hideMenu, { passive: true });
          window.addEventListener('resize', hideMenu);

          menu.addEventListener('click', async (e) => {
            const item = e.target.closest('.item');
            if (!item || item.classList.contains('disabled')) return;
            const action = item.getAttribute('data-action');
            try {
              if (action === 'copy') {
                const text = term.getSelection ? term.getSelection() : '';
                if (!text) return;
                if (navigator.clipboard && navigator.clipboard.writeText) {
                  await navigator.clipboard.writeText(text);
                } else {
                  // Fallback via temporary textarea
                  const ta = document.createElement('textarea');
                  ta.value = text; document.body.appendChild(ta);
                  ta.select(); document.execCommand('copy');
                  document.body.removeChild(ta);
                }
              } else if (action === 'paste') {
                if (navigator.clipboard && navigator.clipboard.readText) {
                  const clip = await navigator.clipboard.readText();
                  if (clip) {
                    if (typeof term.paste === 'function') term.paste(clip);
                    else if (socket && socket.readyState === WebSocket.OPEN) socket.send(clip);
                  }
                } else {
                  alert('Clipboard paste not available in this browser/context. Use Ctrl+V.');
                }
              }
            } catch (err) {
              console.warn('Clipboard error:', err);
            } finally {
              hideMenu();
            }
          });
        }
      </script>
    </body>
    </html>
  `);
  
  popup.document.close();
}

// Slide-in overlay terminal - enhanced and resizable
let term, socket;

function openTerminalOverlay(hostId, hostName, hostAddress) {
  const overlay = document.getElementById("terminal-overlay");
  const panel = document.getElementById("terminal-panel");
  const terminalElement = document.getElementById("terminal");

  // Update close button text to show host info
  const closeButton = document.getElementById("close-terminal");
  if (closeButton) {
    closeButton.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"/>
        <line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
      Close ${hostName}
    `;
  }

  overlay.classList.add("open");
  panel.classList.add("open");

  // Cleanup existing terminal
  if (term) {
    term.dispose();
    term = null;
  }
  if (socket) {
    socket.close();
    socket = null;
  }

  // Initialize new terminal
  term = new Terminal({
    fontFamily: 'Menlo, Monaco, "Courier New", monospace',
    fontSize: 14,
    theme: { 
      background: '#000000',
      foreground: '#ffffff',
      cursor: '#ffffff'
    },
    cursorBlink: true,
    scrollback: 1000,
    allowTransparency: false
  });

  const fitAddon = new FitAddon.FitAddon();
  const webLinksAddon = new WebLinksAddon.WebLinksAddon();
  
  term.loadAddon(fitAddon);
  term.loadAddon(webLinksAddon);
  term.open(terminalElement);

  // Attach context menu for copy/paste on overlay terminal
  try { attachTerminalContextMenu(term, terminalElement); } catch (e) { console.warn('context menu attach failed', e); }

  // Initial fit
  setTimeout(() => {
    fitAddon.fit();
  }, 100);

  // Show connection status
  term.write(`\r\n🔌 Connecting to ${hostName} (${hostAddress})...\r\n`);

  // Connect WebSocket
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${protocol}://${location.host}/ws/${hostId}`;
  
  socket = new WebSocket(wsUrl);
  let isConnected = false;

  socket.onopen = () => {
    console.log("Overlay terminal WebSocket connected");
    isConnected = true;
  };

  socket.onerror = (err) => {
    console.error("Overlay terminal WebSocket error:", err);
    if (!isConnected) {
      term.write("\r\n*** ❌ WebSocket connection failed ***\r\n");
      term.write("*** Please check your network connection ***\r\n");
    }
  };

  socket.onclose = (event) => {
    console.log("Overlay terminal WebSocket disconnected", event.code, event.reason);
    if (isConnected) {
      term.write("\r\n*** 📡 Connection closed ***\r\n");
    }
    isConnected = false;
  };

  socket.onmessage = event => {
    term.write(event.data);
    if (!isConnected) {
      isConnected = true;
    }
  };

  term.onData(data => {
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(data);
    }
  });

  // Handle window resize for overlay terminal
  const resizeHandler = () => {
    if (fitAddon && term) {
      setTimeout(() => {
        fitAddon.fit();
      }, 10);
    }
  };
  
  window.addEventListener("resize", resizeHandler);
  
  // Store resize handler for cleanup
  overlay._resizeHandler = resizeHandler;

  // Connection timeout for overlay
  setTimeout(() => {
    if (!isConnected && socket && socket.readyState !== WebSocket.CLOSED) {
      term.write("\r\n*** ⏱️ Connection timeout ***\r\n");
      term.write("*** The host might be unreachable ***\r\n");
      socket.close();
    }
  }, 30000); // 30 second timeout
}

function closeTerminalOverlay() {
  const overlay = document.getElementById("terminal-overlay");
  const panel = document.getElementById("terminal-panel");
  
  if (socket) {
    socket.close();
    socket = null;
  }
  if (term) {
    term.dispose();
    term = null;
  }

  // Remove resize handler
  if (overlay._resizeHandler) {
    window.removeEventListener("resize", overlay._resizeHandler);
    delete overlay._resizeHandler;
  }

  panel.classList.remove("open");
  overlay.classList.remove("open");
}

// Attach a custom right-click context menu with Copy/Paste for an xterm.js instance
function attachTerminalContextMenu(termInstance, container) {
  if (!container || !termInstance) return;
  // Avoid duplicate menus
  if (container._hasContextMenu) return;
  container._hasContextMenu = true;

  const menu = document.createElement('div');
  menu.className = 'terminal-context-menu';
  menu.innerHTML = `
    <div class="item" data-action="copy">📋 Copy</div>
    <div class="item" data-action="paste">📥 Paste</div>
  `;
  document.body.appendChild(menu);

  function hideMenu() { menu.style.display = 'none'; }
  function showMenu(x, y) {
    const copyItem = menu.querySelector('[data-action="copy"]');
    if (termInstance.hasSelection && termInstance.hasSelection()) copyItem.classList.remove('disabled');
    else copyItem.classList.add('disabled');

    const vw = window.innerWidth, vh = window.innerHeight;
    const rect = { w: menu.offsetWidth || 180, h: menu.offsetHeight || 80 };
    const left = Math.min(x, vw - rect.w - 8);
    const top = Math.min(y, vh - rect.h - 8);
    menu.style.left = left + 'px';
    menu.style.top = top + 'px';
    menu.style.display = 'block';
  }

  container.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    hideMenu();
    showMenu(e.clientX, e.clientY);
  });

  document.addEventListener('click', (e) => { if (!menu.contains(e.target)) hideMenu(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideMenu(); });
  container.addEventListener('wheel', hideMenu, { passive: true });
  window.addEventListener('resize', hideMenu);

  menu.addEventListener('click', async (e) => {
    const item = e.target.closest('.item');
    if (!item || item.classList.contains('disabled')) return;
    const action = item.getAttribute('data-action');
    try {
      if (action === 'copy') {
        const text = termInstance.getSelection ? termInstance.getSelection() : '';
        if (!text) return;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
        } else {
          const ta = document.createElement('textarea');
          ta.value = text; document.body.appendChild(ta);
          ta.select(); document.execCommand('copy');
          document.body.removeChild(ta);
        }
      } else if (action === 'paste') {
        if (navigator.clipboard && navigator.clipboard.readText) {
          const clip = await navigator.clipboard.readText();
          if (clip) {
            if (typeof termInstance.paste === 'function') termInstance.paste(clip);
            else if (socket && socket.readyState === WebSocket.OPEN) socket.send(clip);
          }
        } else {
          alert('Clipboard paste not available in this browser/context. Use Ctrl+V.');
        }
      }
    } catch (err) {
      console.warn('Clipboard error:', err);
    } finally {
      hideMenu();
    }
  });
}

async function openSftp(hostOrId, username, password) {
  try {
    // Resolve SFTP target from config.js (fallbacks included)
    const proto = (window.SFTP_PROTOCOL || (location.protocol === 'https:' ? 'https' : 'http')).replace(/:$/, '');
    const hostName = (window.SFTP_HOST && window.SFTP_HOST.trim()) ? window.SFTP_HOST.trim() : location.hostname;
    const port = (window.SFTP_PORT && String(window.SFTP_PORT).trim()) ? String(window.SFTP_PORT).trim() : '3000';

    // If no args provided, just open the SFTP UI landing page
    if (typeof hostOrId === 'undefined' || hostOrId === null) {
      const url = `${proto}://${hostName}:${port}/`;
      window.open(url, 'sftpBrowser', 'width=1000,height=700,toolbar=no,location=no,status=no');
      return;
    }

    // Prefer server-side lookup by host ID to avoid exposing credentials in the DOM
    let resp;
    if (typeof hostOrId === 'number') {
      resp = await fetch('/api/sftp/mint', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host_id: hostOrId })
      });
    } else {
      // Legacy fallback (will be phased out): browser sends host/username/password to server
      // Server mints an encrypted token; plaintext never goes into the URL.
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
