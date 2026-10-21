# FoodLens: run the local backend with the bundled model on CPU (teammate/dev machine).
#   -Device phone  (default) real phone with Expo Go on the same Wi-Fi; app uses http://<Wi-Fi IP>:8000
#   -Device local  browser on this computer only; app uses http://127.0.0.1:8000
#   -HostIp        force the Wi-Fi IPv4 when auto-detection picks the wrong adapter (VPN, Ethernet)
param(
    [ValidateSet('phone', 'local')]
    [string]$Device = 'phone',
    [int]$Port = 8000,
    [string]$HostIp = '',
    [string]$SupabaseCli = ''
)
# Windows PowerShell 5.1 turns any stderr line of a native tool (supabase, pip, docker) into a
# terminating error under 'Stop'; check exit codes explicitly instead.
$ErrorActionPreference = 'Continue'
function Supabase { if ($SupabaseCli) { & $SupabaseCli @args } else { & npx -y supabase@2.120.0 @args } }
$env:PYTHONIOENCODING = 'utf-8'
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
if (-not (Test-Path 'data\processed\backend-local.json')) { throw 'Chua cai dat. Chay scripts\setup_dev.ps1 truoc.' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop chua chay.' }
Supabase start --exclude 'realtime,imgproxy,postgres-meta,studio,edge-runtime,logflare,vector,supavisor,mailpit' *> 'data\processed\supabase-start.log'
if ($LASTEXITCODE -ne 0) { throw 'Supabase start that bai. Xem data\processed\supabase-start.log (khong gui file nay cho ai).' }
Supabase status -o json 2>$null | Out-File 'data\processed\supabase-local.json' -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Khong doc duoc trang thai Supabase.' }

function Find-WifiIp {
    $candidates = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {
        $_.InterfaceAlias -notmatch 'vEthernet|Loopback|WSL|VPN|Tailscale|ZeroTier|VirtualBox|VMware|Hyper-V' -and
        $_.PrefixOrigin -in 'Dhcp', 'Manual' -and $_.IPAddress -notlike '169.254.*' }
    $wifi = $candidates | Where-Object { $_.InterfaceAlias -match 'Wi-?Fi|Wireless|WLAN' } | Select-Object -First 1
    if ($wifi) { return $wifi.IPAddress }
    return ($candidates | Select-Object -First 1).IPAddress
}

$bindHost = '127.0.0.1'
if ($Device -eq 'phone') {
    $ip = if ($HostIp) { $HostIp } else { Find-WifiIp }
    if (-not $ip) { throw 'Khong tim thay IP Wi-Fi. Ket noi Wi-Fi roi chay lai, hoac them -HostIp <IPv4 trong ipconfig>.' }
    $public = "http://${ip}:54321"; $api = "http://${ip}:$Port"; $bindHost = '0.0.0.0'
    & .venv\Scripts\python.exe scripts\prepare_dev_config.py --public-supabase-url $public
} else {
    $public = 'http://127.0.0.1:54321'; $api = 'http://127.0.0.1:' + $Port
    & .venv\Scripts\python.exe scripts\prepare_dev_config.py
}
if ($LASTEXITCODE -ne 0) { throw 'Tao config that bai.' }

Write-Host "`nTrong app dat:  API_BASE_URL = $api" -ForegroundColor Green
Write-Host "                SUPABASE_URL = $public" -ForegroundColor Green
Write-Host "                SUPABASE_ANON_KEY = gia tri ANON_KEY trong data\processed\supabase-local.json (key public, chi cua may nay)"
if ($Device -eq 'phone') {
    Write-Host "Thu tren dien thoai (cung Wi-Fi): $api/health/ready  -> phai co `"scan`":true" -ForegroundColor Yellow
    Write-Host 'Khong vao duoc: dat Wi-Fi la Private va mo Firewall cong 8000, 8081, 54321 (xem huong dan Phan C).' -ForegroundColor Yellow
}
Write-Host "Swagger tren laptop: http://127.0.0.1:$Port/docs   (Ctrl+C de dung)`n"
$env:FOODLENS_CONFIG_PATH = (Join-Path $Root 'data\processed\backend-dev.json')
& .venv\Scripts\python.exe -m uvicorn backend.app.main:app --host $bindHost --port $Port --no-access-log
