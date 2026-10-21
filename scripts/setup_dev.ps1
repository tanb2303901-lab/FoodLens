# FoodLens: one-command local backend setup for a teammate/dev machine (Windows PowerShell).
# Creates .venv (CPU model runtime), starts a private Supabase local stack, applies all migrations,
# loads the 75-food catalog and the reviewed food descriptions, and writes ignored configs.
# Safe to run again: existing configs and data are kept. Never prints keys.
param(
    [string]$SupabaseVersion = '2.120.0',
    [string]$SupabaseCli = ''   # optional path to a supabase.exe of the same version instead of npx
)
# Windows PowerShell 5.1 turns any stderr line of a native tool (supabase, pip, docker) into a
# terminating error under 'Stop'; check exit codes explicitly instead.
$ErrorActionPreference = 'Continue'
function Supabase { if ($SupabaseCli) { & $SupabaseCli @args } else { & npx -y "supabase@$SupabaseVersion" @args } }
$env:PYTHONIOENCODING = 'utf-8'
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
New-Item -ItemType Directory -Force (Join-Path $Root 'data\processed') | Out-Null

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Need($cmd, $hint) { if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Thieu '$cmd'. $hint" } }

Step '1/7 Kiem tra cong cu da cai'
Need 'docker' 'Cai Docker Desktop va mo no len.'
if (-not $SupabaseCli) { Need 'npx' 'Cai Node.js LTS (co kem npx).' }
Need 'py' 'Cai Python 3.12 tu python.org (tick "Add python.exe to PATH" va "py launcher").'
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop chua chay. Mo Docker Desktop, doi bieu tuong chuyen xanh roi chay lai.' }
& py -3.12 -c "import sys" 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Khong tim thay Python 3.12 (py -3.12). Cai Python 3.12.' }
if (-not (Test-Path 'ml\models\foodlens-yolo11n-20261016-extension4h-v2\weights.pt')) { throw 'Thieu thu muc model trong ml\models. Hay clone lai repo day du.' }

Step '2/7 Tao moi truong Python (.venv) va cai thu vien (lan dau co the mat 5-15 phut)'
if (-not (Test-Path '.venv\Scripts\python.exe')) { & py -3.12 -m venv .venv; if ($LASTEXITCODE -ne 0) { throw 'Tao .venv that bai.' } }
& .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .venv\Scripts\python.exe -m pip install -r ml\requirements-cpu.txt
if ($LASTEXITCODE -ne 0) { throw 'Cai thu vien Python that bai.' }

Step '3/7 Khoi dong Supabase local (lan dau tai image Docker, co the mat 10-20 phut)'
$exclude = 'realtime,imgproxy,postgres-meta,studio,edge-runtime,logflare,vector,supavisor,mailpit'
Supabase start --exclude $exclude *> 'data\processed\supabase-start.log'
if ($LASTEXITCODE -ne 0) { throw 'Supabase start that bai. Xem data\processed\supabase-start.log (khong gui file nay cho ai vi co key).' }
Supabase status -o json 2>$null | Out-File 'data\processed\supabase-local.json' -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Khong doc duoc trang thai Supabase.' }

Step '4/7 Tao config backend rieng cua may nay'
& .venv\Scripts\python.exe scripts\prepare_backend_local.py
if ($LASTEXITCODE -ne 0) { throw 'Tao config backend that bai.' }
& .venv\Scripts\python.exe scripts\prepare_scan_local.py
if ($LASTEXITCODE -ne 0) { throw 'Tao config scan that bai.' }
& .venv\Scripts\python.exe scripts\prepare_dev_config.py
if ($LASTEXITCODE -ne 0) { throw 'Tao config that bai.' }

Step '5/7 Nap danh muc 75 mon'
& .venv\Scripts\python.exe scripts\import_dataset.py --from-identities --apply --report data\processed\setup-catalog.json
if ($LASTEXITCODE -ne 0) { throw 'Nap danh muc that bai.' }

Step '6/7 Nap noi dung gioi thieu mon'
& .venv\Scripts\python.exe scripts\food_content.py apply --apply
if ($LASTEXITCODE -ne 0) { throw 'Nap noi dung that bai.' }

Step '7/7 Kiem tra nhanh'
$count = docker exec -i supabase_db_foodlens-local psql -X -qAt -U postgres -d postgres -c "select count(*) from public.foods"
$described = docker exec -i supabase_db_foodlens-local psql -X -qAt -U postgres -d postgres -c "select count(distinct food_id) from public.food_descriptions where content_status = 'published'"
Write-Host "So mon trong database: $count"
Write-Host "So mon co gioi thieu da duyet: $described"
if ("$count".Trim() -ne '75' -or "$described".Trim() -ne '75') { throw 'Du lieu chua du 75 mon / 75 gioi thieu. Chay lai scripts\setup_dev.ps1.' }
& .venv\Scripts\python.exe -c "import backend.app.main, ultralytics, torch" 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Thu vien backend/model chua cai du. Chay lai scripts\setup_dev.ps1.' }
Write-Host "`nCai dat xong. Chay backend bang:  powershell -ExecutionPolicy Bypass -File scripts\run_dev_backend.ps1" -ForegroundColor Green
