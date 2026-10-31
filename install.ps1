#requires -Version 7.0
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$Root = (Join-Path $env:USERPROFILE '.starlight/clipboard-index'),
    [switch]$Start,
    [switch]$EnableStartup
)
$ErrorActionPreference = 'Stop'
$resolvedRoot = [IO.Path]::GetFullPath($Root)
$privateRoot = [IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.starlight')) + [IO.Path]::DirectorySeparatorChar
if (-not $resolvedRoot.StartsWith($privateRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Install into a named directory under your existing .starlight runtime.'
}
if ($resolvedRoot.IndexOfAny([char[]]'"%') -ge 0) { throw 'The runtime path contains unsupported command characters.' }
$python = (& py -3 -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $python)) { throw 'Python 3 is required.' }
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'The matching pythonw.exe is missing.' }
$files = @('clip.py', 'clip_store.py', 'clip_integrations.py', 'board.html', 'README.md')
$hashes = [ordered]@{}
foreach ($file in $files) {
    $hashes[$file] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PSScriptRoot $file)).Hash.ToLower()
}
$fingerprint = ($hashes.Values -join '')
$bytes = [Text.Encoding]::UTF8.GetBytes($fingerprint)
$digest = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLower().Substring(0,12)
$release = Join-Path $resolvedRoot "runtime/releases/$digest"
$launcher = Join-Path $env:USERPROFILE '.local/bin/clips.cmd'
$startScript = Join-Path $resolvedRoot 'start-clipd.vbs'
if (-not $PSCmdlet.ShouldProcess($resolvedRoot, "Install verified Clipboard release $digest; start=$Start; login startup=$EnableStartup")) { return }
$disk = Get-PSDrive -Name $resolvedRoot.Substring(0,1)
if ($disk.Free -lt 50GB -or ($disk.Free / ($disk.Free + $disk.Used)) -lt 0.08) {
    throw 'Installation is held by the machine storage floor (50 GiB and 8% free).'
}
$stamp = Get-Date -Format 'yyyyMMddTHHmmssfff'
$rollback = Join-Path $resolvedRoot "runtime/rollback/$stamp"
New-Item -ItemType Directory -Path $rollback -Force | Out-Null
foreach ($existing in @($launcher,$startScript,(Join-Path $resolvedRoot 'clip.py'),(Join-Path $resolvedRoot 'board.html'),(Join-Path $resolvedRoot 'install-receipt.json'))) {
    if (Test-Path -LiteralPath $existing -PathType Leaf) {
        Copy-Item -LiteralPath $existing -Destination (Join-Path $rollback ([IO.Path]::GetFileName($existing)))
    }
}
$database = Join-Path $resolvedRoot 'data/clips.sqlite'
if (Test-Path -LiteralPath $database) {
    & $python -c 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); import clip_store; print(clip_store.backup(Path(sys.argv[2])))' $PSScriptRoot $resolvedRoot
    if ($LASTEXITCODE -ne 0) { throw 'Backup failed. Nothing was upgraded.' }
}
$running = & $python -c 'import ctypes; k=ctypes.windll.kernel32; k.OpenMutexW.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_wchar_p]; k.OpenMutexW.restype=ctypes.c_void_p; k.CloseHandle.argtypes=[ctypes.c_void_p]; h=k.OpenMutexW(0x100000,False,r"Local\StarlightClipboardIndex"); print(1 if h else 0); k.CloseHandle(h) if h else None'
if ("$running".Trim() -eq '1') {
    $receiptPath = Join-Path $resolvedRoot 'install-receipt.json'
    if ($EnableStartup -and (Test-Path -LiteralPath $receiptPath)) {
        $installed = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
        if ($installed.release -eq $release -and (Test-Path -LiteralPath $startScript)) {
            foreach ($file in $files) {
                if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $release $file)).Hash.ToLower() -ne $hashes[$file]) {
                    throw 'The active release differs from its recorded source. Stop capture before upgrading.'
                }
            }
            $startupPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'Starlight Clipboard.lnk'
            $startupShell = New-Object -ComObject WScript.Shell
            $link = $startupShell.CreateShortcut($startupPath)
            $link.TargetPath = Join-Path $env:WINDIR 'System32/wscript.exe'
            $link.Arguments = '"' + $startScript + '" watch'
            $link.WorkingDirectory = $resolvedRoot
            $link.Save()
            Copy-Item -LiteralPath $receiptPath -Destination (Join-Path $rollback 'install-receipt-before-startup.json')
            $installed.startup_enabled = $true
            $installed.revision = 'v2'
            $installed | Add-Member -NotePropertyName updated_at -NotePropertyValue ((Get-Date).ToUniversalTime().ToString('o')) -Force
            $installed | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $receiptPath -Encoding utf8
            Write-Output 'Enabled the login shortcut for the already-running, verified release.'
            return
        }
    }
    throw 'An existing collector owns the Windows clipboard lane. Stop it through clips stop, then rerun; the installer will not kill it.'
}
New-Item -ItemType Directory -Path $release -Force | Out-Null
foreach ($file in $files) {
    $destination = Join-Path $release $file
    if (Test-Path -LiteralPath $destination) {
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash.ToLower() -ne $hashes[$file]) {
            throw "Immutable release content changed: $file"
        }
    } else { Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination $destination }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash.ToLower() -ne $hashes[$file]) {
        throw "Release verification failed: $file"
    }
}
& $python (Join-Path $release 'clip.py') self-test
if ($LASTEXITCODE -ne 0) { throw 'Installed release failed its self-test. The active launcher was not changed.' }
$previousClipHome = $env:CLIP_HOME
try {
    $env:CLIP_HOME = $resolvedRoot
    if (Test-Path -LiteralPath $database) {
        & $python (Join-Path $release 'clip.py') reindex
        if ($LASTEXITCODE -ne 0) { throw 'Database migration failed. Retain the pre-upgrade snapshot.' }
    }
} finally {
    if ($null -eq $previousClipHome) { Remove-Item Env:CLIP_HOME -ErrorAction SilentlyContinue }
    else { $env:CLIP_HOME = $previousClipHome }
}
New-Item -ItemType Directory -Path (Split-Path $launcher) -Force | Out-Null
$cmd = "@echo off`r`nset `"CLIP_HOME=$resolvedRoot`"`r`n`"$python`" `"$(Join-Path $release 'clip.py')`" %*`r`n"
[IO.File]::WriteAllText($launcher, $cmd, [Text.UTF8Encoding]::new($false))
$vbs = @"
Option Explicit
Dim sh, action
Set sh = CreateObject("WScript.Shell")
sh.Environment("PROCESS")("CLIP_HOME") = "$resolvedRoot"
action = "watch"
If WScript.Arguments.Count > 0 Then
    If WScript.Arguments(0) = "board" Then action = "board"
End If
sh.Run """" & "$pythonw" & """ """ & "$(Join-Path $release 'clip.py')" & """ " & action, 0, False
"@
[IO.File]::WriteAllText($startScript,$vbs,[Text.UTF8Encoding]::new($false))
$wsh = New-Object -ComObject WScript.Shell
$programs = Join-Path ([Environment]::GetFolderPath('Programs')) 'Starlight'
New-Item -ItemType Directory -Path $programs -Force | Out-Null
foreach ($entry in @(@('Starlight Clipboard','board'),@('Start Clipboard capture','watch'))) {
    $shortcut = $wsh.CreateShortcut((Join-Path $programs ($entry[0]+'.lnk')))
    $shortcut.TargetPath = Join-Path $env:WINDIR 'System32/wscript.exe'
    $shortcut.Arguments = '"' + $startScript + '" ' + $entry[1]
    $shortcut.WorkingDirectory = $resolvedRoot
    $shortcut.Save()
}
$startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'Starlight Clipboard.lnk'
if ($EnableStartup) {
    $shortcut = $wsh.CreateShortcut($startup)
    $shortcut.TargetPath = Join-Path $env:WINDIR 'System32/wscript.exe'
    $shortcut.Arguments = '"' + $startScript + '" watch'
    $shortcut.WorkingDirectory = $resolvedRoot
    $shortcut.Save()
}
$receipt = [ordered]@{
    author='Codex'; created_at=(Get-Date).ToUniversalTime().ToString('o'); revision='v1'
    state='installed-local'; release=$release; files=$hashes; rollback=$rollback
    data_root=$resolvedRoot; launcher=$launcher; startup_enabled=(Test-Path -LiteralPath $startup)
    cloud_processing=$false; auto_delete_history=$false; start_requested=[bool]$Start
}
if ($Start) {
    $env:CLIP_HOME = $resolvedRoot
    try {
        $process = Start-Process -FilePath $pythonw -ArgumentList @(('"' + (Join-Path $release 'clip.py') + '"'),'watch') -WindowStyle Hidden -PassThru
        $receipt['process_id'] = $process.Id
    } finally {
        if ($null -eq $previousClipHome) { Remove-Item Env:CLIP_HOME -ErrorAction SilentlyContinue }
        else { $env:CLIP_HOME = $previousClipHome }
    }
}
$receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $resolvedRoot 'install-receipt.json') -Encoding utf8
$receipt | ConvertTo-Json -Depth 6
