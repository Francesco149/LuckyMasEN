# bootstrap_python.ps1 — fetch a private embeddable Python 3.11 into $PyDir for build.bat.
# Enables site-packages (so pip can install into it) and fetches get-pip.py. One-time, on
# first run; keeps the builder independent of any system Python or the Windows Store alias.
param([Parameter(Mandatory=$true)][string]$PyDir)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ver = '3.11.9'
$zip = Join-Path $env:TEMP 'lm-python-embed.zip'
Write-Host "downloading Python $ver (embeddable)…"
Invoke-WebRequest "https://www.python.org/ftp/python/$ver/python-$ver-embed-amd64.zip" -OutFile $zip
New-Item -Force -ItemType Directory $PyDir | Out-Null
Expand-Archive -Force $zip $PyDir
# the embeddable ships site-packages disabled; turn it on so pip works
$pth = (Get-ChildItem (Join-Path $PyDir 'python*._pth') | Select-Object -First 1).FullName
(Get-Content $pth) -replace '#\s*import site', 'import site' | Set-Content $pth
if (-not (Select-String -Path $pth -Pattern 'Lib\\site-packages' -SimpleMatch -Quiet)) {
    Add-Content $pth 'Lib\site-packages'
}
Write-Host "fetching get-pip.py…"
Invoke-WebRequest 'https://bootstrap.pypa.io/get-pip.py' -OutFile (Join-Path $PyDir 'get-pip.py')
Write-Host "python bootstrap complete: $PyDir"
