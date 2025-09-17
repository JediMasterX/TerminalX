const list = document.getElementById('rangeList');

// Only run if we're on the range generator page
const addRangeBtn = document.getElementById('addRangeBtn');
const exportRangesBtn = document.getElementById('exportRangesBtn');

if (addRangeBtn && list) {
  addRangeBtn.onclick = () => {
    const v = document.getElementById('rangeInput').value.trim();
    if (!v) return;
    const parts = v.split(',').map(s => s.trim());
    const ips = [];
    parts.forEach(part => {
      if (part.includes('-') && part.indexOf('.') !== -1) {
        const [startIP, endSuffix] = part.split('-');
        const prefix = startIP.substring(0, startIP.lastIndexOf('.') + 1);
        const start = parseInt(startIP.substring(startIP.lastIndexOf('.') + 1));
        const end = parseInt(endSuffix);
        for (let i = start; i <= end; i++) {
          ips.push(prefix + i);
        }
      } else {
        ips.push(part);
      }
    });
    ips.forEach(ip => {
      const existing = Array.from(list.children).map(li => li.textContent);
      if (!existing.includes(ip)) {
        const li = document.createElement('li');
        li.textContent = ip;
        list.append(li);
      }
    });
  };
}

if (exportRangesBtn && list) {
  exportRangesBtn.onclick = () => {
    const items = Array.from(list.children).map(li => li.textContent).join('\n');
    const blob = new Blob([items], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'ranges.txt'; a.click();
    URL.revokeObjectURL(url);
  };
}