$ErrorActionPreference = 'Stop'
$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# __VERSION__ and __SHA256__ are filled in by the release workflow
$packageArgs = @{
  PackageName    = $env:ChocolateyPackageName
  FileFullPath   = Join-Path $toolsDir 'mangabinder.exe'
  Url64bit       = 'https://github.com/Preygle/manga-downloader/releases/download/v__VERSION__/mangabinder.exe'
  Checksum64     = '__SHA256__'
  ChecksumType64 = 'sha256'
}
# Chocolatey adds a `mangabinder` shim for the downloaded exe automatically
Get-ChocolateyWebFile @packageArgs
