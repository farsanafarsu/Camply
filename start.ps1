# Start Camply locally: MongoDB (if not already running), then the Django app, then open the browser.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File start.ps1   (or double-click start.bat)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

function Test-Port([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect("127.0.0.1", $port, $null, $null)
        return $connect.AsyncWaitHandle.WaitOne(500) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Python environment not found. Run these first:" -ForegroundColor Red
    Write-Host "  python -m venv .venv"
    Write-Host "  .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# 1. MongoDB
if (Test-Port 27017) {
    Write-Host "MongoDB is already running on port 27017." -ForegroundColor Green
} else {
    $mongod = Get-ChildItem -Path (Join-Path $root ".mongodb") -Filter mongod.exe -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $mongod) {
        Write-Host "MongoDB isn't running and no portable copy was found in .mongodb\." -ForegroundColor Red
        Write-Host "Start MongoDB yourself (or run: docker compose up -d), then run this script again."
        exit 1
    }
    $dataDir = Join-Path $root ".mongodb\data"
    New-Item -ItemType Directory -Force $dataDir | Out-Null
    Write-Host "Starting MongoDB..."
    Start-Process -FilePath $mongod.FullName `
        -ArgumentList "--dbpath", "`"$dataDir`"", "--bind_ip", "127.0.0.1", "--port", "27017", "--quiet" `
        -WindowStyle Minimized
    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-Port 27017)) {
        if ((Get-Date) -gt $deadline) {
            Write-Host "MongoDB didn't start within 30 seconds." -ForegroundColor Red
            exit 1
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "MongoDB is running." -ForegroundColor Green
}

# 2. Django app
if (Test-Port 8000) {
    Write-Host "Camply is already running." -ForegroundColor Green
    Start-Process "http://127.0.0.1:8000"
    exit 0
}

& $python manage.py migrate --noinput | Out-Null
Write-Host "Starting Camply at http://127.0.0.1:8000 (press Ctrl+C to stop)..." -ForegroundColor Green
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 3
    Start-Process "http://127.0.0.1:8000"
} | Out-Null
& $python manage.py runserver 127.0.0.1:8000
