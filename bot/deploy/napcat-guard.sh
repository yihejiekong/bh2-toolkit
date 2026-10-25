#!/bin/bash
# NapCat 守护脚本：容器 + QQ 进程 + NapCat HTTP 端口 三路检测
#  - 异常 -> docker restart napcat，最多等 90 秒复查
#  - 恢复后把「掉线时长」写进 pending.jsonl，由 bot 插件 guard_alert 私聊推给管理员
#  - 5 分钟内不重复重启，避免风暴
set -u

LOG_DIR=/var/log/napcat-guard
STATE=$LOG_DIR/state
LATE=$LOG_DIR/last_restart
PENDING=$LOG_DIR/pending.jsonl
EVENTS=$LOG_DIR/events.log

mkdir -p "$LOG_DIR" 2>/dev/null

# 告警文件要与 bot（ubuntu 用户）共用：目录 775、文件 root:ubuntu 664
[ -f "$PENDING" ] || { : > "$PENDING" 2>/dev/null; }
chown root:ubuntu "$PENDING" 2>/dev/null || true
chmod 664 "$PENDING" 2>/dev/null
chown root:ubuntu "$LOG_DIR" 2>/dev/null || true
chmod 775 "$LOG_DIR" 2>/dev/null

now() { date +%s; }
ts() { date '+%F %T'; }

check_container() {
    [ "$(docker inspect -f '{{.State.Running}}' napcat 2>/dev/null)" = "true" ]
}

check_qq() {
    pgrep -f '/opt/QQ/qq --no-sandbox -q' >/dev/null 2>&1
}

check_http() {
    local code
    code=$(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:6099/ 2>/dev/null)
    [ -n "${code:-}" ] && [ "$code" != "000" ]
}

healthy() {
    check_container && check_qq && check_http
}

record() {  # $1=event  $2=since
    local dur=$(( $(now) - $2 ))
    printf '{"kind":"napcat","event":"%s","at":%s,"down_at":%s,"duration":%s}\n' \
        "$1" "$(now)" "$2" "$dur" >> "$PENDING"
    chmod 664 "$PENDING" 2>/dev/null
}

main() {
    if healthy; then
        if [ -f "$STATE" ]; then
            local since dur
            since=$(cat "$STATE" 2>/dev/null || echo "$(now)")
            dur=$(( $(now) - since ))
            rm -f "$STATE"
            echo "[$(ts)] RECOVERED after ${dur}s (no restart needed)" >> "$EVENTS"
            record recover "$since"
        fi
        exit 0
    fi

    local since
    if [ ! -f "$STATE" ]; then
        now > "$STATE"
    fi
    since=$(cat "$STATE" 2>/dev/null || echo "$(now)")

    echo "[$(ts)] UNHEALTHY container=$([ "$(docker inspect -f '{{.State.Running}}' napcat 2>/dev/null)" = "true" ] && echo y || echo n) qq=$(check_qq && echo y || echo n) http=$(check_http && echo y || echo n)" >> "$EVENTS"

    # 冷却：5 分钟内不重复重启
    local late=0
    [ -f "$LATE" ] && late=$(cat "$LATE" 2>/dev/null || echo 0)
    if [ $(( $(now) - late )) -lt 300 ]; then
        echo "[$(ts)] SKIP restart (cooldown $(( $(now) - late ))s)" >> "$EVENTS"
        exit 0
    fi
    now > "$LATE"

    docker restart napcat >/dev/null 2>&1
    echo "[$(ts)] RESTART issued" >> "$EVENTS"

    for _ in $(seq 1 30); do
        sleep 3
        if healthy; then
            local dur
            dur=$(( $(now) - since ))
            rm -f "$STATE"
            echo "[$(ts)] RESTARTED OK after ${dur}s" >> "$EVENTS"
            record restart "$since"
            exit 0
        fi
    done
    echo "[$(ts)] RESTART FAILED (still unhealthy after 90s)" >> "$EVENTS"
}

main
