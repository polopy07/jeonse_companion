"""시연 전 DB 초기화: 모든 표를 지우고 다시 만든 뒤 시연 집 실거래 저장본을 넣는다.

판정·계약·할 일과 증빙 사진(EVIDENCE_DIR)이 모두 지워진다. 시연 노트북에서 리허설·시연 직전에 쓴다.
backend/ 폴더에서 DATABASE_URL을 서버와 같게 두고 실행: python reset_demo_db.py (확인 없이: --yes)
SQLite는 서버를 끄고 실행한다 (서버가 파일을 잡고 있으면 지우지 못할 수 있음). 앱이 저장해 둔 예전 계약은
서버에 없으면(404) 앱이 지운다.
"""
import sys

from sqlalchemy.engine import make_url

from app import evidence
from app.config import database_url
from app.db import Base, get_engine, init_db
from load_demo_trades import load


def reset() -> tuple[str, int]:
    """기준일과 넣은 실거래 건수를 돌려준다."""
    from app import models  # noqa: F401  (표 등록)

    engine = get_engine()
    Base.metadata.drop_all(engine)
    init_db(engine)
    evidence.remove_all()   # 지운 할 일의 증빙 사진도 (계약별 폴더만)
    return load()


if __name__ == "__main__":
    url = make_url(database_url())
    target = f"SQLite 파일 {url.database}" if url.get_backend_name() == "sqlite" else url.render_as_string(hide_password=True)
    if "--yes" not in sys.argv:
        answer = input(f"{target}의 판정·계약·할 일을 모두 지우고 시연 상태로 되돌립니다. 계속할까요? (y/N) ")
        if answer.strip().lower() != "y":
            sys.exit("취소했습니다")
    as_of, added = reset()
    print(f"초기화 끝: {target}, 실거래 저장본 기준일 {as_of} {added}건. 서버를 다시 켜세요")
