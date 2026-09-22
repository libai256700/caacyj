#!/usr/bin/env bash
set -e

APP_DIR=/home/soft/jar/yunjikeji-admin-server
JAR_NAME=yunjikeji-admin-server.jar
LOG_DIR=/home/soft/logs/yunjikeji-admin-server
LOG_FILE=$LOG_DIR/yunjikeji-admin-server.log
PID_FILE=$APP_DIR/yunjikeji-admin-server.pid

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

PIDS=$(pgrep -f "$APP_DIR/$JAR_NAME|$JAR_NAME --spring.profiles.active=test" || true)
if [ -n "$PIDS" ]; then
  echo "$PIDS" | xargs -r kill
  sleep 5
  PIDS=$(pgrep -f "$APP_DIR/$JAR_NAME|$JAR_NAME --spring.profiles.active=test" || true)
  if [ -n "$PIDS" ]; then
    echo "$PIDS" | xargs -r kill -9
  fi
fi

nohup java -Xms256m -Xmx512m -XX:MaxMetaspaceSize=256m -Xss512k -jar "$APP_DIR/$JAR_NAME" --spring.profiles.active=test >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "started pid=$(cat "$PID_FILE") log=$LOG_FILE"
