$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $projectRoot 'Setup Desktop Shortcut.ps1')
$runtimeRoot = Join-Path $projectRoot 'runtime'
$fixture = Join-Path $runtimeRoot ('desktop shortcut verification ' + [Guid]::NewGuid().ToString('N'))
$desktopFixture = Join-Path $fixture 'Desktop with spaces'
$projectFixture = Join-Path $fixture 'Project with spaces'
$otherFixture = Join-Path $fixture 'Other installation'
$shell = $null
try {
    New-Item -ItemType Directory -Path $desktopFixture, $projectFixture, $otherFixture -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot 'Start Rumi Dental Care.cmd') -Destination $projectFixture
    Copy-Item -LiteralPath (Join-Path $projectRoot 'Start Rumi Dental Care.cmd') -Destination $otherFixture
    foreach ($folder in @($projectFixture, $otherFixture)) {
        New-Item -ItemType Directory -Path (Join-Path $folder '.venv\Scripts'), (Join-Path $folder 'scripts') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $folder '.venv\Scripts\pythonw.exe') -Value 'fixture only'
        Copy-Item -LiteralPath (Join-Path $projectRoot 'scripts\desktop.pyw') -Destination (Join-Path $folder 'scripts')
    }
    $first = Install-RumiDesktopShortcut -ProjectDirectory $projectFixture -DesktopDirectory $desktopFixture
    if ($first.Result -ne 'Created') { throw 'Expected a new shortcut.' }
    $second = Install-RumiDesktopShortcut -ProjectDirectory $projectFixture -DesktopDirectory $desktopFixture
    if ($second.Result -ne 'Updated same installation') { throw 'Same-installation rerun failed.' }
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($first.Shortcut)
    if ($link.TargetPath -ne (Join-Path $projectFixture '.venv\Scripts\pythonw.exe') -or
        $link.WorkingDirectory -ne $projectFixture -or $link.Arguments -ne ('"' + (Join-Path $projectFixture 'scripts\desktop.pyw') + '"') -or $link.WindowStyle -ne 1) {
        throw 'Target, working directory, arguments or visible-console settings differ.'
    }
    Write-Output 'PASS: spaces in project/Desktop paths, exact launcher target, working directory, empty arguments, normal window, built-in icon and same-installation rerun.'
    $link.TargetPath = Join-Path $otherFixture 'Start Rumi Dental Care.cmd'
    $link.Save()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)
    $before = (Get-FileHash -LiteralPath $first.Shortcut -Algorithm SHA256).Hash
    $conflict = $false
    try { Install-RumiDesktopShortcut -ProjectDirectory $projectFixture -DesktopDirectory $desktopFixture | Out-Null }
    catch { $conflict = $_.Exception.Message.StartsWith('Conflict:') }
    if (-not $conflict -or (Get-FileHash -LiteralPath $first.Shortcut -Algorithm SHA256).Hash -ne $before) {
        throw 'A shortcut for another installation was not preserved.'
    }
    Write-Output 'PASS: another installation produces a conflict and its shortcut stays byte-for-byte unchanged.'
    $link = $shell.CreateShortcut($first.Shortcut)
    $link.TargetPath = Join-Path $projectFixture 'Start Rumi Dental Care.cmd'
    $link.Arguments = '--custom-test-only'
    $link.Save()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)
    $before = (Get-FileHash -LiteralPath $first.Shortcut -Algorithm SHA256).Hash
    $conflict = $false
    try { Install-RumiDesktopShortcut -ProjectDirectory $projectFixture -DesktopDirectory $desktopFixture | Out-Null }
    catch { $conflict = $_.Exception.Message.StartsWith('Conflict:') }
    if (-not $conflict -or (Get-FileHash -LiteralPath $first.Shortcut -Algorithm SHA256).Hash -ne $before) {
        throw 'Customized shortcut was not preserved.'
    }
    Write-Output 'PASS: custom arguments are preserved without displaying them; no credentials or elevation are added.'
    $stop = Install-RumiDesktopShortcut -ProjectDirectory $projectFixture -DesktopDirectory $desktopFixture -Stop
    $link = $shell.CreateShortcut($stop.Shortcut)
    if (-not $link.Arguments.EndsWith(' --stop')) { throw 'Stop control argument missing.' }
    Write-Output 'PASS: separate no-console Start and Stop shortcuts verified.'
}
finally {
    if ($null -ne $shell) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) }
    if (Test-Path -LiteralPath $fixture) {
        # Check the absolute fixture boundary before any recursive cleanup.
        $resolvedFixture = (Resolve-Path -LiteralPath $fixture).ProviderPath
        $resolvedRuntime = [IO.Path]::GetFullPath($runtimeRoot).TrimEnd('\') + '\'
        if (-not $resolvedFixture.StartsWith($resolvedRuntime, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Refusing cleanup outside the runtime fixture directory.'
        }
        Remove-Item -LiteralPath $resolvedFixture -Recurse -Force
    }
}
