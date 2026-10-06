param(
    [string]$BackupRoot = "D:\InventoryBackups",
    [int]$KeepDays = 30
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$ProjectData = Join-Path $ProjectRoot "data"
$LogFile = Join-Path $BackupRoot "backup.log"

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Get-PythonPath {
    $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundled) {
        return $bundled
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) {
        return $cmd.Source
    }
    $cmd = Get-Command py -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) {
        return $cmd.Source
    }
    return ""
}

try {
    if (-not (Test-Path -LiteralPath $ProjectData)) {
        throw "未找到数据目录：$ProjectData"
    }
    if (-not (Test-Path -LiteralPath $BackupRoot)) {
        New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    }

    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $zipPath = Join-Path $BackupRoot "inventory_backup_$stamp.zip"
    $staging = Join-Path $env:TEMP ("inventory_backup_staging_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $staging "data") -Force | Out-Null

    try {
        Get-ChildItem -LiteralPath $ProjectRoot -Force |
            Where-Object { $_.Name -ne "__pycache__" } |
            Copy-Item -Destination $staging -Recurse -Force

        $srcDb = Join-Path $ProjectData "inventory.db"
        $stageDb = Join-Path $staging "inventory.db"
        $python = Get-PythonPath
        $dbBackedUp = $false

        if ($python -and (Test-Path -LiteralPath $srcDb)) {
            $env:INVENTORY_SQLITE_SRC = $srcDb
            $env:INVENTORY_SQLITE_DST = $stageDb
            $code = "import os, sqlite3; src=os.environ['INVENTORY_SQLITE_SRC']; dst=os.environ['INVENTORY_SQLITE_DST']; s=sqlite3.connect(src); d=sqlite3.connect(dst); s.backup(d); d.close(); s.close()"
            & $python -c $code
            if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $stageDb)) {
                $dbBackedUp = $true
            }
        }

        if (-not $dbBackedUp -and (Test-Path -LiteralPath $srcDb)) {
            Copy-Item -LiteralPath $srcDb -Destination $stageDb -Force
        }

        Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -CompressionLevel Optimal
    }
    finally {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -LiteralPath $staging -Recurse -Force
        }
    }

    $cutoff = (Get-Date).AddDays(-$KeepDays)
    $removed = 0
    Get-ChildItem -LiteralPath $BackupRoot -Filter "inventory_backup_*.zip" |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Force
            $removed++
        }

    Write-Log "备份完成：$zipPath"
    Write-Log "已清理 $removed 个超过 $KeepDays 天的旧备份。"
    exit 0
}
catch {
    Write-Log "备份失败：$($_.Exception.Message)"
    exit 1
}
