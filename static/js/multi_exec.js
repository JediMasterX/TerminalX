let ws;
let busy = false;
const hostViews = new Map();
let summary = { total: 0, started: 0, success: 0, failure: 0 };

function showExamples() {
  alert(
    'Examples:\n'
    + '  ls -al /var/log ; df -h ; uname -a\n'
    + '  df -h\n'
    + '  Chaining commands: use && to run next only if previous succeeds, or || to run next only if previous fails.\n'
    + '    e.g.: ls /nonexistent && echo "Success" || echo "Failure"'
  );
}
function exportLog() {
  const text = document.getElementById('output').textContent;
  const blob = new Blob([text], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'terminal.log';
  a.click();
  URL.revokeObjectURL(url);
}

function connect() {
  if (busy) return; // prevent double submit while running
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  busy = true;
  setButtonsState(true);
  clearOutput();

  const fileInput = document.getElementById('hostFile');
  const sshUser = document.getElementById('sshUser').value;
  const sshPass = document.getElementById('sshPass').value;
  const raw = document.getElementById('command').value.trim();
  let command = raw;

  if (raw.startsWith('sudo ')) {
    let inner = raw.replace(/^sudo\s+/, '');
    if (/^apt\s+update/.test(inner)) {
      inner = inner.replace(/^apt\s+update/, 'DEBIAN_FRONTEND=noninteractive apt-get update -y');
    }
    command = `echo '${sshPass}' | sudo -S -p '' ${inner}`;
  }

  const range = document.getElementById('hostRange').value;
  const hostsPromise = fileInput.files.length
    ? readFileLines(fileInput.files[0])
    : Promise.resolve([]);

  hostsPromise.then(fileLines => {
    startWebsocket(range, sshUser, sshPass, command, fileLines);
  });
}

function startWebsocket(range, user, pw, cmd, fileLines) {
  ws = new WebSocket(`ws://${location.host}/ws`);

  ws.onopen = () => {
    appendSystem(`Launching command: ${cmd}`);
    ws.send(JSON.stringify({ host_range: range, hosts_file_lines: fileLines, ssh_user: user, ssh_pass: pw, command: cmd }));
  };

  ws.onmessage = evt => {
    const msg = JSON.parse(evt.data);
    handleMessage(msg);
  };

  ws.onclose = () => {
    appendSystem('Execution stopped.');
    busy = false;
    setButtonsState(false);
    updateSummaryBadge();
    // Finalize any hosts that are still in running/connecting state
    hostViews.forEach((view, host) => {
      const stage = view.status.dataset.stage;
      if (stage === 'connecting' || stage === 'command_starting' || stage === 'command_started' || stage === 'connected') {
        setStatus(host, 'stopped');
      }
    });
  };
}

function stopAll() {
  if (ws) try { ws.close(); } catch {}
}

function ensureHostView(host) {
  if (hostViews.has(host)) return hostViews.get(host);
  const container = document.getElementById('output');
  const section = document.createElement('section');
  section.className = 'host-section';

  const header = document.createElement('div');
  header.className = 'host-header';
  const title = document.createElement('span');
  title.className = 'host-title';
  title.textContent = host;
  const status = document.createElement('span');
  status.className = 'host-status badge status-idle';
  status.textContent = 'pending';
  header.append(title, status);

  const pre = document.createElement('pre');
  pre.className = 'host-output';
  pre.dataset.host = host;

  section.append(header, pre);
  container.append(section);
  const view = { section, header, title, status, pre };
  hostViews.set(host, view);
  return view;
}

function appendSystem(text) {
  const now = new Date().toLocaleTimeString();
  const pre = document.createElement('pre');
  pre.textContent = `[${now}] [SYSTEM] ${text}`;
  document.getElementById('output').append(pre);
}

function setStatus(host, stage, extra) {
  const view = ensureHostView(host);
  const map = {
    connecting: 'Connecting…',
    connected: 'Connected',
    command_starting: 'Starting…',
    command_started: 'Running',
    completed: extra && extra.ok ? 'Success' : 'Failed',
    connect_failed: 'Connect failed',
    error: 'Error',
    stopped: 'Stopped'
  };
  view.status.textContent = map[stage] || stage;
  view.status.dataset.stage = stage;
  // Update visual classes
  view.status.classList.remove('status-idle','status-connecting','status-running','status-ok','status-failed','status-error','status-stopped');
  if (stage === 'connecting' || stage === 'connected' || stage === 'command_starting') {
    view.status.classList.add('status-connecting');
  } else if (stage === 'command_started') {
    view.status.classList.add('status-running');
  } else if (stage === 'completed') {
    view.status.classList.add(extra && extra.ok ? 'status-ok' : 'status-failed');
  } else if (stage === 'connect_failed' || stage === 'error') {
    view.status.classList.add('status-error');
  } else if (stage === 'stopped') {
    view.status.classList.add('status-stopped');
  }
}

function appendHostOutput(host, stream, data) {
  const view = ensureHostView(host);
  const now = new Date().toLocaleTimeString();
  if (stream === 'stderr' && (!data || data.trim() === '')) {
    return; // skip empty stderr chunks to avoid stray ERR> lines
  }
  const prefix = stream === 'stderr' ? 'ERR> ' : '';
  // Keep as a single text node append to reduce DOM churn
  view.pre.append(document.createTextNode(`[${now}] ${prefix}${data}`));
}

function handleMessage(msg) {
  if (msg.type === 'init') {
    summary = { total: msg.total_hosts || 0, started: 0, success: 0, failure: 0 };
    appendSystem(`Dispatching to ${msg.total_hosts} host(s)…`);
    updateSummaryBadge();
    return;
  }
  if (msg.type === 'host_status') {
    setStatus(msg.host, msg.stage, msg);
    if (msg.stage === 'connected') {
      summary.started += 1;
    } else if (msg.stage === 'completed') {
      if (msg.ok) summary.success += 1; else summary.failure += 1;
    } else if (msg.stage === 'connect_failed' || msg.stage === 'error') {
      summary.failure += 1;
    }
    updateSummaryBadge();
    return;
  }
  if (msg.type === 'output') {
    appendHostOutput(msg.host, msg.stream, msg.data);
    return;
  }
  if (msg.type === 'summary') {
    appendSystem(`Summary: total=${msg.total_hosts}, started=${msg.started}, success=${msg.success}, failure=${msg.failure}, duration=${msg.duration_sec}s`);
    summary = { total: msg.total_hosts, started: msg.started, success: msg.success, failure: msg.failure };
    updateSummaryBadge();
    return;
  }
  if (msg.type === 'error') {
    appendSystem(`Error: ${msg.message || 'unknown error'}`);
    return;
  }
}

function updateSummaryBadge() {
  const el = document.getElementById('output-summary');
  if (!el) return;
  const remaining = Math.max(0, (summary.total || 0) - (summary.success + summary.failure));
  el.textContent = `OK ${summary.success} · Fail ${summary.failure} · Pending ${remaining}`;
}

function filterOutput() {
  const term = document.getElementById('filterInput').value;
  document.querySelectorAll('#output pre').forEach(el => {
    el.style.display = el.textContent.includes(term) ? '' : 'none';
  });
}

function clearOutput() {
  document.getElementById('output').innerHTML = '';
  hostViews.clear();
}

function readFileLines(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result.split(/\r?\n/).filter(Boolean));
    fr.onerror = reject;
    fr.readAsText(file);
  });
}

function setButtonsState(running) {
  const runBtn = document.getElementById('runBtn');
  const stopBtn = document.getElementById('stopBtn');
  if (running) {
    runBtn.disabled = true;
    runBtn.setAttribute('aria-busy', 'true');
    stopBtn.disabled = false;
  } else {
    runBtn.disabled = false;
    runBtn.removeAttribute('aria-busy');
    stopBtn.disabled = true;
  }
}

// Collapsible Output Panel
function openOutputPanel() {
  const panel = document.getElementById('output-panel');
  const toggle = document.getElementById('output-toggle');
  const icon = document.getElementById('output-toggle-icon');
  if (!panel || !toggle || !icon) return;
  panel.classList.remove('collapsed');
  toggle.setAttribute('aria-expanded', 'true');
  icon.textContent = '▾';
}

function toggleOutputPanel() {
  const panel = document.getElementById('output-panel');
  const toggle = document.getElementById('output-toggle');
  const icon = document.getElementById('output-toggle-icon');
  if (!panel || !toggle || !icon) return;
  const isCollapsed = panel.classList.toggle('collapsed');
  toggle.setAttribute('aria-expanded', String(!isCollapsed));
  icon.textContent = isCollapsed ? '▸' : '▾';
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('runBtn').onclick = connect;
  document.getElementById('stopBtn').onclick = stopAll;
  document.getElementById('exportBtn').onclick = exportLog;
  setButtonsState(false);
  const toggle = document.getElementById('output-toggle');
  if (toggle) toggle.onclick = toggleOutputPanel;
});

// Override summary calculation to derive from current host statuses
function updateSummaryBadge() {
  const el = document.getElementById('output-summary');
  if (!el) return;
  let ok = 0, fail = 0;
  hostViews.forEach(view => {
    const cls = view.status.classList;
    if (cls.contains('status-ok')) ok++;
    else if (cls.contains('status-failed') || cls.contains('status-error')) fail++;
    else {
      const stage = view.status.dataset.stage;
      if (stage === 'connect_failed' || stage === 'error') fail++;
    }
  });
  const total = summary.total || hostViews.size || 0;
  const remaining = Math.max(0, total - (ok + fail));
  el.textContent = `OK ${ok} · Fail ${fail} · Pending ${remaining}`;
}


