param([string]$Distribution = 'Debian')
$ErrorActionPreference = 'Stop'
& wsl.exe --distribution $Distribution --cd $PSScriptRoot -- bash ./windows-entry.sh
if ($LASTEXITCODE -ne 0) { throw "Chatbox build failed. Exit code: $LASTEXITCODE" }
