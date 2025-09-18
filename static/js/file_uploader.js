// Only run if we're on the file uploader page
const uploadBtn = document.getElementById("uploadBtn");
if (uploadBtn) {
  uploadBtn.addEventListener("click", async () => {
    const output = document.getElementById("uploadOutput");
    if (!output) return;
    
    output.textContent = "📤 Preparing upload...\n";

    const sshUser = document.getElementById("sshUser");
    const sshPass = document.getElementById("sshPass");
    const file = document.getElementById("fileUpload");
    const remotePath = document.getElementById("remotePath");
    const ipFileInput = document.getElementById("ipFileInput");
    const hostRange = document.getElementById("hostRange");

    if (!sshUser || !sshPass || !file || !remotePath || !hostRange) {
      output.textContent += "❌ Required elements not found on page.\n";
      return;
    }

    const sshUserValue = sshUser.value.trim();
    const sshPassValue = sshPass.value.trim();
    const fileValue = file.files[0];
    const remotePathValue = remotePath.value.trim();
    const ipFileInputValue = ipFileInput ? ipFileInput.files[0] : null;
    const hostsRaw = hostRange.value.trim();

    if (!sshUserValue || !sshPassValue || !fileValue) {
      output.textContent += "❌ All fields are required.\n";
      return;
    }

    let hosts = [];

    if (ipFileInputValue) {
      const text = await ipFileInputValue.text();
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
    formData.append("ssh_user", sshUserValue);
    formData.append("ssh_pass", sshPassValue);
    formData.append("hosts", JSON.stringify(hosts));
    formData.append("file", fileValue);
    formData.append("remote_path", remotePathValue);

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
}

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