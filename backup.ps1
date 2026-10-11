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
        # 必须落在 staging\data\ 下：上面递归复制出来的 data\inventory.db 是热拷贝，
        # 如果一致性快照写到 staging 根目录，打包出来的 zip 里 data\inventory.db
        # 仍是那份不一致的热拷贝，快照则丢在压缩包根目录，恢复时用不上。
        $stageDb = Join-Path (Join-Path $staging "data") "inventory.db"
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

        # 先确认归档真的写出来了再往下走：下面会按保留期删旧备份，
        # 如果这次压缩静默失败，旧的又删了，等于只剩一个坏包。
        if (-not (Test-Path -LiteralPath $zipPath)) {
            throw "备份归档未生成：$zipPath"
        }
        if ((Get-Item -LiteralPath $zipPath).Length -eq 0) {
            throw "备份归档为空：$zipPath"
        }
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
    # 日志目录可能还没建起来（例如 $ProjectData 缺失时在 try 里更早就抛了），
    # 这里再写日志如果也失败，会把真正的错误盖掉，所以兜一层。
    if (-not (Test-Path -LiteralPath $BackupRoot)) {
        try { New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null } catch { }
    }
    try {
        Write-Log "备份失败：$($_.Exception.Message)"
    }
    catch {
        Write-Host "备份失败：$($_.Exception.Message)"
    }
    exit 1
}
