param(
    [Parameter(Mandatory = $true)][string]$DataDirectory,
    [switch]$Update,
    [string]$Wheelhouse
)
$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot
if (-not [IO.Path]::IsPathRooted($DataDirectory)) { throw 'DataDirectory must be an explicit absolute existing path.' }
$data = (Resolve-Path -LiteralPath $DataDirectory).ProviderPath
if ($env:RUMI_DATA_DIR -and [IO.Path]::GetFullPath($env:RUMI_DATA_DIR) -ne $data) { throw 'Conflicting RUMI_DATA_DIR; resolve the selection first.' }
foreach ($name in @('clinic.sqlite3', 'secret.key')) {
    if (-not (Test-Path -LiteralPath (Join-Path $data $name) -PathType Leaf)) { throw 'Existing runtime missing. Recover existing data first; no replacement accounts will be created.' }
}
Push-Location -LiteralPath $project
try {
    $python = Join-Path $project '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        & py -3.13 -m venv (Join-Path $project '.venv')
        if ($LASTEXITCODE) { throw 'Supported Python 3.13 is required.' }
    }
    & $python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,13) else 1)'
    if ($LASTEXITCODE) { throw 'This installation requires Python 3.13.' }
    $pipArgs = @('-m', 'pip', 'install', '-r', (Join-Path $project 'requirements.txt'))
    if ($Wheelhouse) { $pipArgs += @('--no-index', '--find-links', (Resolve-Path -LiteralPath $Wheelhouse).ProviderPath) }
    & $python @pipArgs
    if ($LASTEXITCODE) { throw 'Dependency installation failed. No migrations applied.' }
    & $python -m pip check
    if ($LASTEXITCODE) { throw 'Dependency check failed.' }
    $maintenance = @((Join-Path $project 'scripts\local_update.py'), '--data-dir', $data)
    if ($Update) { $maintenance += '--apply' }
    & $python @maintenance
    if ($LASTEXITCODE) { throw 'Maintenance stopped; review the diagnostic above. No data-directory relocation was performed.' }
    Write-Host 'Setup checks passed. Root desktop shortcuts intentionally select this checkout runtime\development.'
} finally { Pop-Location }
