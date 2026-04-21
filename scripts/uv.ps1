$ErrorActionPreference = "Stop"

# 專案限定 uv wrapper：固定使用工作區內的 cache，避免全域 uv cache 權限或污染問題。
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$env:UV_CACHE_DIR = Join-Path $ProjectRoot ".uv-cache"

if ($args.Count -eq 0) {
    Write-Host "Usage: .\scripts\uv.ps1 run pytest"
    Write-Host "Usage: .\scripts\uv.ps1 run ruff check src tests"
    exit 2
}

Push-Location $ProjectRoot
try {
    & uv @args
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $exitCode
