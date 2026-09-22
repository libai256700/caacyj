$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RemoteHost = 'test-3dapp'
$RemoteWebDir = '/home/soft/web/yunjikeji-admin'
$RemoteTmpDir = '/home/soft/tmp'
$BuildDir = Join-Path $ProjectRoot 'dist-testhost'
$ArchivePath = Join-Path $env:TEMP ("yunjikeji-admin-web-{0}.tar.gz" -f (Get-Date -Format 'yyyyMMddHHmmss'))
$NginxSnippet = Join-Path $PSScriptRoot 'nginx-test.conf'

Push-Location $ProjectRoot
try {
    pnpm build:testhost
    if (-not (Test-Path $BuildDir)) {
        throw "Build output not found: $BuildDir"
    }
    tar.exe -czf $ArchivePath -C $BuildDir .
    scp $ArchivePath "${RemoteHost}:${RemoteTmpDir}/"
    scp $NginxSnippet "${RemoteHost}:${RemoteTmpDir}/"
    $RemoteArchive = "${RemoteTmpDir}/" + [IO.Path]::GetFileName($ArchivePath)
    $RemoteNginxSnippet = "${RemoteTmpDir}/" + [IO.Path]::GetFileName($NginxSnippet)
    $remoteCmd = @'
set -e
STAMP=$(date +%Y%m%d%H%M%S)
BACKUP_DIR=/home/soft/backup/$STAMP/yunjikeji-admin-web
mkdir -p "$BACKUP_DIR"
if [ -d "__REMOTE_WEB_DIR__" ]; then
  cp -a "__REMOTE_WEB_DIR__" "$BACKUP_DIR/"
fi
rm -rf "__REMOTE_WEB_DIR__"
mkdir -p "__REMOTE_WEB_DIR__"
tar -xzf "__REMOTE_ARCHIVE__" -C "__REMOTE_WEB_DIR__"
rm -f "__REMOTE_ARCHIVE__"
cp "__REMOTE_NGINX_SNIPPET__" /home/soft/tmp/yunjikeji-admin-nginx.conf
rm -f "__REMOTE_NGINX_SNIPPET__"
'@
    $remoteCmd = $remoteCmd.Replace('__REMOTE_WEB_DIR__', $RemoteWebDir).Replace('__REMOTE_ARCHIVE__', $RemoteArchive).Replace('__REMOTE_NGINX_SNIPPET__', $RemoteNginxSnippet)
    ssh $RemoteHost $remoteCmd
}
finally {
    Pop-Location
    if (Test-Path $ArchivePath) {
        Remove-Item $ArchivePath -Force
    }
}
