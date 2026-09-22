$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RemoteHost = 'test-3dapp'
$RemoteWebDir = '/home/soft/web/yunjikeji'
$RemoteTmpDir = '/home/soft/tmp'
$BuildDir = Join-Path $ProjectRoot 'dist\build\h5'
$ArchivePath = Join-Path $env:TEMP ("yunjikeji-web-{0}.tar.gz" -f (Get-Date -Format 'yyyyMMddHHmmss'))

Push-Location $ProjectRoot
try {
    npm run build:h5:test
    if (-not (Test-Path $BuildDir)) {
        throw "Build output not found: $BuildDir"
    }
    tar.exe -czf $ArchivePath -C $BuildDir .
    scp $ArchivePath "${RemoteHost}:${RemoteTmpDir}/"
    $RemoteArchive = "${RemoteTmpDir}/" + [IO.Path]::GetFileName($ArchivePath)
    $remoteCmd = @'
set -e
STAMP=$(date +%Y%m%d%H%M%S)
BACKUP_DIR=/home/soft/backup/$STAMP/yunjikeji-web
mkdir -p "$BACKUP_DIR"
if [ -d "__REMOTE_WEB_DIR__" ]; then
  cp -a "__REMOTE_WEB_DIR__/." "$BACKUP_DIR/"
fi
rm -rf "__REMOTE_WEB_DIR__"
mkdir -p "__REMOTE_WEB_DIR__"
tar -xzf "__REMOTE_ARCHIVE__" -C "__REMOTE_WEB_DIR__"
rm -f "__REMOTE_ARCHIVE__"
curl -I -s https://yunjikeji.lai-do.com/ >/dev/null
'@
    $remoteCmd = $remoteCmd.Replace('__REMOTE_WEB_DIR__', $RemoteWebDir).Replace('__REMOTE_ARCHIVE__', $RemoteArchive)
    # Pass the POSIX script as UTF-8 Base64 so SSH never turns its line endings into CRLF.
    $remoteCmd = $remoteCmd -replace "`r`n", "`n"
    $remoteCmdBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteCmd))
    ssh $RemoteHost "echo $remoteCmdBase64 | base64 -d | bash"
}
finally {
    Pop-Location
    if (Test-Path $ArchivePath) {
        Remove-Item $ArchivePath -Force
    }
}
