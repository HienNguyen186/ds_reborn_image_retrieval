param(
    [ValidateSet('doctor', 'index', 'serve', 'dev', 'test', 'build', 'frontend')]
    [string]$Mode = 'serve',
    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectDir 'env\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Khong tim thay env\Scripts\python.exe. Tao venv va cai backend\requirements-image-search.txt truoc.'
}

if ($Mode -in 'serve', 'dev') {
    # Do this before loading another copy of the model into GPU memory.
    $portProbe = New-Object System.Net.Sockets.TcpClient
    $portBusy = $false
    try {
        $connection = $portProbe.ConnectAsync('127.0.0.1', 8000)
        if ($connection.Wait(1000)) { $portBusy = $portProbe.Connected }
    }
    catch { $portBusy = $false }
    finally { $portProbe.Dispose() }

    if ($portBusy) {
        $isOurBackend = $false
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 3 -ErrorAction Stop
            $schema = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 3 -ErrorAction Stop
            $isOurBackend = $health.status -eq 'ok' -and $schema.info.title -like 'DS Reborn*'
        }
        catch { $isOurBackend = $false }
        if ($isOurBackend) {
            Write-Host 'Backend DS Reborn da dang chay: http://127.0.0.1:8000'
            Write-Host 'Khong khoi dong them. Mo trinh duyet de su dung.'
            Write-Host 'Neu can khoi dong lai, nhan Ctrl+C trong terminal server cu, roi chay lai lenh.'
            return
        }
        throw 'Cong 8000 dang duoc mot dich vu khac su dung hoac backend chua san sang. Kiem tra terminal server cu; launcher khong tu dung tien trinh khac.'
    }
}

Push-Location (Join-Path $projectDir 'backend')
try {
    switch ($Mode) {
        'doctor' { & $pythonExe -X utf8 -m src.image_retrieval.cli doctor }
        'index' {
            $indexArgs = @('-X', 'utf8', '-m', 'src.image_retrieval.cli', 'index')
            if ($Rebuild) { $indexArgs += '--rebuild' }
            & $pythonExe @indexArgs
        }
        'test' { & $pythonExe -X utf8 -m unittest discover -s tests -p 'test_image*.py' -v }
        'serve' {
            if (-not (Test-Path -LiteralPath (Join-Path $projectDir 'frontend\dist\index.html'))) {
                throw 'Chay backend\run.ps1 -Mode build truoc; frontend source duoc giu nguyen.'
            }
            & $pythonExe -X utf8 -m uvicorn main:app --host 127.0.0.1 --port 8000
        }
        'dev' { & $pythonExe -X utf8 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload }
        { $_ -in 'build', 'frontend' } {
            # Process-only override: never edit frontend/.env or any UI source.
            $previousApiBase = $env:VITE_API_BASE_URL
            $previousDresUrl = $env:VITE_SUBMISSION
            $previousDresUser = $env:VITE_TEAM_ID
            $previousDresPassword = $env:VITE_TEAM_PASSWORD
            try {
                $env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
                $dresConfig = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs\dres.json') -Raw | ConvertFrom-Json
                $env:VITE_SUBMISSION = $dresConfig.base_url
                $env:VITE_TEAM_ID = $dresConfig.username
                if ($Mode -eq 'build') {
                    $env:VITE_TEAM_PASSWORD = ''
                }
                else {
                    # Let Vite read the user's ignored development-local defaults.
                    Remove-Item Env:VITE_TEAM_PASSWORD -ErrorAction SilentlyContinue
                }
                $npmMode = if ($Mode -eq 'build') { 'build' } else { 'dev' }
                & npm --prefix (Join-Path $projectDir 'frontend') run $npmMode
            }
            finally {
                if ($null -eq $previousApiBase) { Remove-Item Env:VITE_API_BASE_URL -ErrorAction SilentlyContinue }
                else { $env:VITE_API_BASE_URL = $previousApiBase }
                foreach ($savedSetting in @(
                    @{ Name = 'VITE_SUBMISSION'; Value = $previousDresUrl },
                    @{ Name = 'VITE_TEAM_ID'; Value = $previousDresUser },
                    @{ Name = 'VITE_TEAM_PASSWORD'; Value = $previousDresPassword }
                )) {
                    if ($null -eq $savedSetting.Value) { Remove-Item -LiteralPath "Env:$($savedSetting.Name)" -ErrorAction SilentlyContinue }
                    else { Set-Item -LiteralPath "Env:$($savedSetting.Name)" -Value $savedSetting.Value }
                }
            }
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "Lenh that bai (exit $LASTEXITCODE)." }
}
finally { Pop-Location }
