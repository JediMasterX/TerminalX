$folder = "xterm_offline"
New-Item -ItemType Directory -Force -Path $folder | Out-Null
Set-Location $folder

$files = @{
  "xterm.js"                  = "https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"
  "xterm.css"                 = "https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css"
  "xterm-addon-fit.js"        = "https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js"
  "xterm-addon-web-links.js"  = "https://cdn.jsdelivr.net/npm/xterm-addon-web-links@0.8.0/lib/xterm-addon-web-links.js"
  "xterm-addon-unicode11.js" = "https://cdn.jsdelivr.net/npm/xterm-addon-unicode11@0.8.0/dist/xterm-addon-unicode11.js"
  "xterm-addon-search.js"     = "https://cdn.jsdelivr.net/npm/xterm-addon-search@0.8.0/lib/xterm-addon-search.js"
  "xterm-addon-serialize.js"  = "https://cdn.jsdelivr.net/npm/xterm-addon-serialize@0.8.0/lib/xterm-addon-serialize.js"
}

foreach ($name in $files.Keys) {
  $url = $files[$name]
  try {
    Invoke-WebRequest -Uri $url -OutFile $name -ErrorAction Stop
    Write-Host "Downloaded: $name"
  } catch {
    Write-Warning "Failed: $name from $url"
  }
}
