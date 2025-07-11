document.getElementById("uploadBtn").addEventListener("click", async () => {
  const output = document.getElementById("uploadOutput");
  output.textContent = "📤 Preparing upload...\n";

  const sshUser = document.getElementById("sshUser").value.trim();
  const sshPass = document.getElementById("sshPass").value.trim();
  const file = document.getElementById("fileUpload").files[0];
  const remotePath = document.getElementById("remotePath").value.trim();
  const ipFileInput = document.getElementById("ipFileInput").files[0];
  const hostsRaw = document.getElementById("hostRange").value.trim();

  if (!sshUser || !sshPass || !file) {
    output.textContent += "❌ All fields are required.\n";
    return;
  }

  let hosts = [];

  if (ipFileInput) {
    const text = await ipFileInput.text();
    hosts = text.split(/\r?\n/).map(line => line.trim()).filter(line => line);
    if (hosts.length === 0) {
      output.textContent += "❌ No valid IPs found in uploaded file.\n";
      return;
    }
  } else if (hostsRaw) {
    if (hostsRaw.includes("-")) {
      hosts = expandRange(hostsRaw);
    } else if (hostsRaw.includes(",")) {
      hosts = hostsRaw.split(",").map(h => h.trim()).filter(h => h);
    } else {
      hosts = [hostsRaw];
    }
  } else {
    output.textContent += "❌ You must provide host IPs (via range OR file upload).\n";
    return;
  }

  // STEP 1: Upload the form data first
  const formData = new FormData();
  formData.append("ssh_user", sshUser);
  formData.append("ssh_pass", sshPass);
  formData.append("hosts", JSON.stringify(hosts));
  formData.append("file", file);
  formData.append("remote_path", remotePath);

  const res = await fetch("/upload_file", {
    method: "POST",
    body: formData
  });

  if (!res.ok) {
    output.textContent += `❌ Upload failed: HTTP ${res.status}\n`;
    return;
  }

  // STEP 2: Start streaming the upload logs
  const stream = res.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { value, done } = await stream.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });

    chunk.split("\n\n").forEach(line => {
      if (line.startsWith("data: ")) {
        output.textContent += line.slice(6) + "\n";
        output.scrollTop = output.scrollHeight;
      }
    });
  }
});

function expandRange(rangeStr) {
  const match = rangeStr.match(/(\d+\.\d+\.\d+\.)(\d+)-(\d+)/);
  if (!match) return [rangeStr];
  const [_, base, start, end] = match;
  const list = [];
  for (let i = parseInt(start); i <= parseInt(end); i++) {
    list.push(base + i);
  }
  return list;
}
