#!/usr/bin/env bash
# 동아 클라우드 VM(Ubuntu 24.04)에 전동기 백엔드를 처음 설치한다 (docs/guide/배포_방법.md).
# 저장소 폴더에서: bash deploy/setup_vm.sh https://<VM이름>-<아이디>.apps.dauai.org
# 여러 번 돌려도 된다: 이미 있는 backend/.env와 DB는 그대로 두고, 패키지·자동 실행 설정만 다시 맞춘다.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC_URL="${1:-}"
SERVICE=jeonse-backend
ENV_FILE="$REPO/backend/.env"
# backend/.env를 서버(uvicorn --env-file)와 같은 방식으로 읽고 시연 DB를 초기화한다 (셸로 읽으면 띄어쓰기 든 값이 깨짐)
RESET_WITH_ENV='from dotenv import load_dotenv; load_dotenv(".env"); import runpy; runpy.run_path("reset_demo_db.py", run_name="__main__")'

echo "== 1. 파이썬 가상환경과 패키지"
if ! python3 -m venv --help >/dev/null 2>&1 || ! dpkg -s python3-venv >/dev/null 2>&1; then
    sudo apt-get update -q
    sudo apt-get install -y -q python3-venv
fi
[ -d "$REPO/.venv" ] || python3 -m venv "$REPO/.venv"
"$REPO/.venv/bin/pip" install -q --upgrade pip
"$REPO/.venv/bin/pip" install -q -r "$REPO/backend/requirements.txt"

echo "== 2. 서버 설정 backend/.env"
if [ -f "$ENV_FILE" ]; then
    echo "이미 있음: 그대로 둠 ($ENV_FILE)"
else
    ADMIN_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    cat > "$ENV_FILE" <<EOF
# 배포 서버 설정 (deploy/setup_vm.sh가 만듦, git에 올리지 않음). 항목 설명은 backend/.env.example
DATABASE_URL=sqlite:///$REPO/backend/data/jeonse.db
EVIDENCE_DIR=$REPO/backend/data/evidence
REQUIRE_CONTRACT_AUTH=true
# 시연을 이 서버에서 하므로 가상 날짜를 받는다. 실제 서비스로 쓸 때는 false
ALLOW_VIRTUAL_TODAY=true
ADMIN_TOKEN=$ADMIN_TOKEN
PUBLIC_BASE_URL=$PUBLIC_URL
# 실제 메일 발송은 smtp로 바꾸고 SMTP_* 채우기 (Gmail은 앱 비밀번호)
EMAIL_BACKEND=console
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=
# SMTP_PASSWORD=
# SMTP_FROM=
# 접근 링크 메일의 링크 앞부분 (예: 앱 딥링크). 비워 두면 링크 대신 접근 코드를 보낸다
# APP_LINK_BASE=
# 공공데이터포털 키 (실거래가를 새로 받을 때만, 시연은 저장본이라 필요 없음)
DATA_GO_KR_SERVICE_KEY=
# 브이월드 인증키 (주소로 공시가격 찾기, 비우면 직접 입력). 서비스 주소는 PUBLIC_BASE_URL
# VWORLD_API_KEY=
CORS_ORIGINS=
EOF
    chmod 600 "$ENV_FILE"
    echo "만듦: $ENV_FILE (관리자 토큰 ADMIN_TOKEN은 이 파일에 있음)"
    [ -n "$PUBLIC_URL" ] || echo "주의: 배포 주소를 넘기지 않아 PUBLIC_BASE_URL이 비어 있음 (캘린더 구독 주소가 배포 주소로 나오지 않을 수 있음)"
fi
mkdir -p "$REPO/backend/data"

echo "== 3. 시연 DB (없을 때만 만듦)"
if [ -f "$REPO/backend/data/jeonse.db" ]; then
    echo "이미 있음: 그대로 둠 (초기화는 deploy/update.sh --reset)"
else
    (cd "$REPO/backend" && "$REPO/.venv/bin/python" -c "$RESET_WITH_ENV" --yes)
fi

echo "== 4. 자동 실행 (systemd)"
sed -e "s#__USER__#$(whoami)#g" -e "s#__REPO__#$REPO#g" "$REPO/deploy/$SERVICE.service" \
    | sudo tee "/etc/systemd/system/$SERVICE.service" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE"
sudo systemctl restart "$SERVICE"

echo "== 5. 확인"
for _ in $(seq 1 15); do
    if curl -fsS http://127.0.0.1:8000/health 2>/dev/null; then
        echo
        echo "서버가 떴습니다. VM 상세 화면 \"포트\"에 8000을 저장하고 ${PUBLIC_URL:-배포 주소}/health 를 열어 보세요"
        exit 0
    fi
    sleep 1
done
echo "서버가 뜨지 않았습니다. 로그: journalctl -u $SERVICE -n 50 --no-pager" >&2
exit 1
