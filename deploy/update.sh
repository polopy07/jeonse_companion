#!/usr/bin/env bash
# 배포 서버를 main 최신으로 바꾸고 다시 띄운다 (docs/guide/배포_방법.md).
# 저장소 폴더에서: bash deploy/update.sh          → 코드만 바꿈 (DB·증빙은 그대로)
#                  bash deploy/update.sh --reset  → 시연 DB도 초기화 (판정·계약·할 일·증빙을 모두 지움, 리허설·시연 직전)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE=jeonse-backend
# backend/.env를 서버(uvicorn --env-file)와 같은 방식으로 읽고 시연 DB를 초기화한다 (셸로 읽으면 띄어쓰기 든 값이 깨짐)
RESET_WITH_ENV='from dotenv import load_dotenv; load_dotenv(".env"); import runpy; runpy.run_path("reset_demo_db.py", run_name="__main__")'
cd "$REPO"

git pull --ff-only origin main
"$REPO/.venv/bin/pip" install -q -r backend/requirements.txt

sudo systemctl stop "$SERVICE"
if [ "${1:-}" = "--reset" ]; then
    # 서버를 끈 상태에서 (SQLite 파일을 서버가 잡고 있지 않게)
    (cd backend && "$REPO/.venv/bin/python" -c "$RESET_WITH_ENV" --yes)
fi
sudo systemctl start "$SERVICE"

for _ in $(seq 1 15); do
    if curl -fsS http://127.0.0.1:8000/health; then
        echo
        echo "다시 떴습니다: $(git log --oneline -1)"
        exit 0
    fi
    sleep 1
done
echo "서버가 뜨지 않았습니다. 로그: journalctl -u $SERVICE -n 50 --no-pager" >&2
exit 1
