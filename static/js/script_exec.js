function expandRange(rng) {
  const lastDot = rng.lastIndexOf('.');
  const base = rng.slice(0, lastDot);
  const suffix = rng.slice(lastDot + 1);
  const [start, end] = suffix.split('-').map(s => parseInt(s, 10));
  if (isNaN(start) || isNaN(end) || end < start) {
    throw new Error('Invalid IP range: ' + rng);
  }
  const hosts = [];
  for (let i = start; i <= end; i++) {
    hosts.push(`${base}.${i}`);
  }
  return hosts;
}

// Helper to read host list from file or range input
function getHosts() {
  const fileInput = document.getElementById('hostFile');
  if (fileInput.files.length) {
    return new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => {
        const lines = fr.result.split(/\r?\n/).filter(Boolean);
        resolve(lines.flatMap(line =>
          line.includes('-') && line.includes('.')
            ? expandRange(line.trim())
            : [line.trim()]
        ));
      };
      fr.onerror = reject;
      fr.readAsText(fileInput.files[0]);
    });
  }

  const rng = document.getElementById('hostRange').value.trim();
  if (!rng) return Promise.resolve([]);
  // single shorthand range or single IP
  if (rng.includes('-') && rng.includes('.')) {
    return Promise.resolve(expandRange(rng));
  }
  return Promise.resolve([rng]);
}

// Export the script execution log
function exportScriptLog() {
  const text = document.getElementById('scriptOutput').textContent;
  const blob = new Blob([text], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'script.log';
  a.click();
  URL.revokeObjectURL(url);
}

let scriptController;

// Handle upload and run with abort capability
async function uploadAndRun() {
  const outputEl = document.getElementById('scriptOutput');
  outputEl.textContent = '[SYSTEM] Starting script execution...\n';
  scriptController = new AbortController();

  try {
    const hosts = await getHosts();
    if (!hosts.length) throw new Error('No hosts provided');

    outputEl.textContent += `[SYSTEM] Hosts: ${hosts.join(', ')}\n`;
    const file = document.getElementById('scriptFile').files[0];
    if (!file) throw new Error('No script file selected');

    const sshUser = document.getElementById('sshUser').value;
    const sshPass = document.getElementById('sshPass').value;
    const sudo = document.getElementById('runSudo').checked;

    outputEl.textContent += '[SYSTEM] Uploading script to hosts...\n';
    const form = new FormData();
    form.append('script', file);
    form.append('hosts', JSON.stringify(hosts));
    form.append('ssh_user', sshUser);
    form.append('ssh_pass', sshPass);
    form.append('sudo', sudo);

    const res = await fetch('/run_script', {
      method: 'POST',
      body: form,
      signal: scriptController.signal
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(`Server error: ${err}`);
    }

    const log = await res.text();
    outputEl.textContent += log;
  } catch (err) {
    if (err.name === 'AbortError') {
      outputEl.textContent += '[SYSTEM] Script execution aborted.\n';
    } else {
      outputEl.textContent += `[ERROR] ${err.message}\n`;
    }
  }
}

function stopScript() {
  if (scriptController) scriptController.abort();
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('uploadRunBtn').onclick = uploadAndRun;
  document.getElementById('stopScriptBtn').onclick = stopScript;
  document.getElementById('exportScriptBtn').onclick = exportScriptLog;
});