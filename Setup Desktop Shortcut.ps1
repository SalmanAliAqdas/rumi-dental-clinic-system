# Phase 1 trial convenience only. No elevation, credentials or global settings.
$ErrorActionPreference = 'Stop'

function Install-RumiDesktopShortcut {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectDirectory,
        [Parameter(Mandatory = $true)][string]$DesktopDirectory
    )

    $project = (Resolve-Path -LiteralPath $ProjectDirectory).ProviderPath
    $desktop = (Resolve-Path -LiteralPath $DesktopDirectory).ProviderPath
    $launcher = Join-Path $project 'Start Rumi Dental Care.cmd'
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw 'The existing Start Rumi Dental Care.cmd launcher is missing. No shortcut was created.'
    }
    $destination = Join-Path $desktop 'Rumi Dental Care.lnk'
    $temporary = Join-Path $desktop ('.RumiDesktopShortcut-' + [Guid]::NewGuid().ToString('N') + '.lnk')
    $shell = $null
    $existing = $null
    $shortcut = $null
    $verified = $null
    $disposition = 'Created'
    try {
        $shell = New-Object -ComObject WScript.Shell
        if (Test-Path -LiteralPath $destination) {
            if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) {
                throw ('Conflict: ' + $destination + ' exists but is not a shortcut file. It was preserved.')
            }
            $existing = $shell.CreateShortcut($destination)
            $oldTarget = [Environment]::ExpandEnvironmentVariables($existing.TargetPath)
            if ([string]::IsNullOrWhiteSpace($oldTarget) -or -not [string]::Equals(
                [IO.Path]::GetFullPath($oldTarget), $launcher, [StringComparison]::OrdinalIgnoreCase)) {
                throw ('Conflict: the existing Rumi Dental Care shortcut targets another location: ' + $oldTarget + '. It was preserved. Confirm its installation before renaming/removing that shortcut yourself and rerunning setup.')
            }
            if (-not [string]::IsNullOrWhiteSpace($existing.Arguments)) {
                throw 'Conflict: the existing shortcut has custom arguments. It was preserved; review it locally before replacing it. Its arguments are not displayed.'
            }
            $disposition = 'Updated same installation'
        }

        # Use a supplied clinic ICO only at these explicit local asset locations.
        # No logo/image is generated or downloaded by this script.
        $iconFile = $null
        foreach ($relativeIcon in @('static\rumi-dental-care.ico', 'static\clinic.ico')) {
            $candidate = Join-Path $project $relativeIcon
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                $iconFile = $candidate
                break
            }
        }
        if (-not $iconFile) {
            # The familiar blue built-in Windows console icon, not a clinic logo.
            $iconFile = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::System)) 'WindowsPowerShell\v1.0\powershell.exe'
            if (-not (Test-Path -LiteralPath $iconFile -PathType Leaf)) {
                $iconFile = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::System)) 'shell32.dll'
            }
        }
        $iconLocation = $iconFile + ',0'
        # Start from a new file so old arguments/elevation flags cannot carry over.
        $shortcut = $shell.CreateShortcut($temporary)
        $shortcut.TargetPath = $launcher
        $shortcut.WorkingDirectory = $project
        $shortcut.Arguments = ''
        $shortcut.WindowStyle = 1
        $shortcut.Description = 'Rumi Dental Care - Phase 1 local trial. Sign in with your existing clinic account.'
        $shortcut.IconLocation = $iconLocation
        $shortcut.Save()
        $verified = $shell.CreateShortcut($temporary)
        if ($verified.TargetPath -ne $launcher -or $verified.WorkingDirectory -ne $project -or
            $verified.Arguments -ne '' -or $verified.WindowStyle -ne 1 -or
            $verified.IconLocation -ne $iconLocation) {
            throw 'Shortcut verification failed; the existing desktop entry was not replaced.'
        }
        $bytes = [IO.File]::ReadAllBytes($temporary)
        if ($bytes.Length -lt 0x18 -or ([BitConverter]::ToUInt32($bytes, 0x14) -band 0x2000) -ne 0) {
            throw 'Shortcut verification failed: unexpected elevation flags. No desktop entry was replaced.'
        }
        Move-Item -LiteralPath $temporary -Destination $destination -Force
        [pscustomobject]@{
            Result = $disposition
            Shortcut = $destination
            Target = $launcher
            WorkingDirectory = $project
            Icon = $iconLocation
            WindowStyle = 1
            AdministratorRequired = $false
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporary -PathType Leaf) {
            Remove-Item -LiteralPath $temporary
        }
        foreach ($comObject in @($verified, $shortcut, $existing, $shell)) {
            if ($null -ne $comObject -and [Runtime.InteropServices.Marshal]::IsComObject($comObject)) {
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($comObject)
            }
        }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    # Windows resolves redirected/OneDrive Desktop locations for the current user.
    $actualDesktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
    if ([string]::IsNullOrWhiteSpace($actualDesktop) -or -not (Test-Path -LiteralPath $actualDesktop -PathType Container)) {
        throw 'Windows did not return an available Desktop folder. Nothing was created; check Desktop/OneDrive availability.'
    }
    Install-RumiDesktopShortcut -ProjectDirectory $PSScriptRoot -DesktopDirectory $actualDesktop | Format-List
    Write-Host 'Double-click Rumi Dental Care on your desktop, then sign in. Keep the server console open; Ctrl+C stops it.'
}
