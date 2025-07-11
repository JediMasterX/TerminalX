let ws;

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
  if (ws) ws.close();
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
    appendOutput('SYSTEM', `Launching command: ${cmd}`);
    ws.send(JSON.stringify({ host_range: range, hosts_file_lines: fileLines, ssh_user: user, ssh_pass: pw, command: cmd }));
  };

  ws.onmessage = evt => {
    const msg = JSON.parse(evt.data);
    appendOutput(msg.host, msg.output);
  };

  ws.onclose = () => appendOutput('SYSTEM', 'Execution stopped.');
}

function stopAll() {
  if (ws) ws.close();
}

function appendOutput(host, text) {
  const now = new Date().toLocaleTimeString();
  const pre = document.createElement('pre');
  pre.textContent = `[${now}] [${host}] ${text}`;
  document.getElementById('output').append(pre);
}

function filterOutput() {
  const term = document.getElementById('filterInput').value;
  document.querySelectorAll('#output pre').forEach(el => {
    el.style.display = el.textContent.includes(term) ? '' : 'none';
  });
}

function clearOutput() {
  document.getElementById('output').innerHTML = '';
}

function readFileLines(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result.split(/\r?\n/).filter(Boolean));
    fr.onerror = reject;
    fr.readAsText(file);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('runBtn').onclick = connect;
  document.getElementById('stopBtn').onclick = stopAll;
  document.getElementById('exportBtn').onclick = exportLog;
});