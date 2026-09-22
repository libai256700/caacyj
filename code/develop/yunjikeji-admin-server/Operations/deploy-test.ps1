$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RemoteHost = 'test-3dapp'
$RemoteJarDir = '/home/soft/jar/yunjikeji-admin-server'
$RemoteScript = '/home/soft/script/yunjikeji-admin-server-start.sh'
$RemoteTmpDir = '/home/soft/tmp'
$JarPath = Join-Path $ProjectRoot 'yunjikeji-admin-server\target\yunjikeji-admin-server.jar'
$LocalStartScript = Join-Path $PSScriptRoot 'yunjikeji-admin-server-start.sh'
$LocalWechatOpenEnv = Join-Path $PSScriptRoot 'test-wechat-open.env'
$MavenSettings = Join-Path $PSScriptRoot 'maven-central-settings.xml'
$DeployWechatOpenConfig = $false

if (Test-Path $LocalWechatOpenEnv) {
    $wechatOpenSecret = Get-Content -LiteralPath $LocalWechatOpenEnv |
        Where-Object { $_ -match '^\s*WX_OPEN_SECRET\s*=\s*(.+?)\s*$' } |
        ForEach-Object { $Matches[1].Trim() } |
        Select-Object -First 1
    $DeployWechatOpenConfig = -not [string]::IsNullOrWhiteSpace($wechatOpenSecret)
}

Push-Location $ProjectRoot
try {
    & mvn '-s' $MavenSettings '-pl' 'yunjikeji-admin-server' '-am' '-Dmaven.test.skip=true' 'clean' 'package'
    if (-not (Test-Path $JarPath)) {
        throw "Jar not found: $JarPath"
    }
    scp $JarPath "${RemoteHost}:${RemoteTmpDir}/"
    scp $LocalStartScript "${RemoteHost}:${RemoteTmpDir}/"
    if ($DeployWechatOpenConfig) {
        scp $LocalWechatOpenEnv "${RemoteHost}:${RemoteTmpDir}/"
    }
    $RemoteJar = "${RemoteTmpDir}/" + [IO.Path]::GetFileName($JarPath)
    $RemoteStartScript = "${RemoteTmpDir}/" + [IO.Path]::GetFileName($LocalStartScript)
    $RemoteWechatOpenEnv = if ($DeployWechatOpenConfig) { "${RemoteTmpDir}/" + [IO.Path]::GetFileName($LocalWechatOpenEnv) } else { '' }
    $remoteCmd = @'
set -e
STAMP=$(date +%Y%m%d%H%M%S)
BACKUP_DIR=/home/soft/backup/$STAMP/yunjikeji-admin-server
mkdir -p "$BACKUP_DIR"
if [ -d "__REMOTE_JAR_DIR__" ]; then
  cp -a "__REMOTE_JAR_DIR__" "$BACKUP_DIR/"
fi
if [ -f "__REMOTE_SCRIPT__" ]; then
  cp -a "__REMOTE_SCRIPT__" "$BACKUP_DIR/"
fi
mkdir -p "__REMOTE_JAR_DIR__"
if [ -n "__REMOTE_WECHAT_OPEN_ENV__" ] && [ -f "__REMOTE_WECHAT_OPEN_ENV__" ]; then
  set -a
  . "__REMOTE_WECHAT_OPEN_ENV__"
  set +a
  if [ -z "${WX_OPEN_SECRET:-}" ]; then
    echo "WX_OPEN_SECRET is empty" >&2
    exit 1
  fi
  if [ "${WX_OPEN_APP_ID:-}" != "wxb23c9af2376126ea" ]; then
    echo "Unexpected WX_OPEN_APP_ID" >&2
    exit 1
  fi
  ENV_FILE="__REMOTE_JAR_DIR__/yunjikeji-bos.env"
  touch "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  TEMP_ENV=$(mktemp "__REMOTE_JAR_DIR__/.yunjikeji-bos.env.XXXXXX")
  awk -F= '$1 != "WX_OPEN_APP_ID" && $1 != "WX_OPEN_SECRET"' "$ENV_FILE" > "$TEMP_ENV"
  printf 'WX_OPEN_APP_ID=%s\nWX_OPEN_SECRET=%s\n' "$WX_OPEN_APP_ID" "$WX_OPEN_SECRET" >> "$TEMP_ENV"
  chmod 600 "$TEMP_ENV"
  mv "$TEMP_ENV" "$ENV_FILE"
fi
cp "__REMOTE_JAR__" "__REMOTE_JAR_DIR__/yunjikeji-admin-server.jar"
cp "__REMOTE_START_SCRIPT__" "__REMOTE_SCRIPT__"
chmod +x "__REMOTE_SCRIPT__"
sed -i 's/\r$//' "__REMOTE_SCRIPT__"
rm -f "__REMOTE_JAR__" "__REMOTE_START_SCRIPT__" "__REMOTE_WECHAT_OPEN_ENV__"
bash "__REMOTE_SCRIPT__"
for i in $(seq 1 45); do
  if curl -fsS http://127.0.0.1:18081/actuator/health >/dev/null; then
    exit 0
  fi
  sleep 2
done
echo "Health check failed: http://127.0.0.1:18081/actuator/health" >&2
exit 1
'@
    $remoteCmd = $remoteCmd.Replace('__REMOTE_JAR_DIR__', $RemoteJarDir).Replace('__REMOTE_SCRIPT__', $RemoteScript).Replace('__REMOTE_JAR__', $RemoteJar).Replace('__REMOTE_START_SCRIPT__', $RemoteStartScript).Replace('__REMOTE_WECHAT_OPEN_ENV__', $RemoteWechatOpenEnv)
    $remoteCmd = $remoteCmd -replace "`r`n", "`n"
    ssh $RemoteHost $remoteCmd
}
finally {
    Pop-Location
}
