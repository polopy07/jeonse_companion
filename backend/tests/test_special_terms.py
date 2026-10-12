"""특약 예시 (app/engine/special_terms.py). API 쪽은 tests/test_api.py."""
import copy

from app.engine.special_terms import contract_day_guide


def test_every_term_action_is_understood(rules):
    # MVP 밖 규칙·특약을 켜도 모든 동작을 읽을 수 있어야 한다 (모르는 동작이면 서버 오류)
    all_on = copy.deepcopy(rules)
    for r in all_on["linkage"]["rules"]:
        r["mvp"] = True
    for t in all_on["special_terms"]["terms"]:
        t["mvp"] = True
    guide = contract_day_guide([r["id"] for r in all_on["linkage"]["rules"]], all_on)
    by_id = {t.id: t for t in guide.terms}
    assert set(by_id) == {"S-NO-MORTGAGE", "S-GUARANTEE-CANCEL", "S-TAX-CERT"}
    assert [t.id for t in by_id["S-TAX-CERT"].if_rejected.adds_todos] == ["X-HUG-LANDLORD-RISK"]
    assert by_id["S-TAX-CERT"].if_inserted.documents == ["국세·지방세 완납증명서"]
    # 같은 특약이 두 연동 규칙에 걸리면 둘 다 표시 (L-RATIO90, L-VIOLATION)
    assert [r.id for r in by_id["S-GUARANTEE-CANCEL"].linked] == ["L-RATIO90", "L-VIOLATION"]


def test_only_mvp_rules_in_mvp(rules):
    guide = contract_day_guide(["L-MORTGAGE", "L-VIOLATION", "L-TAX"], rules)
    assert [t.id for t in guide.terms] == ["S-NO-MORTGAGE"]


def test_removed_linkage_is_skipped(rules):
    # 규칙 파일에서 없어진 연동 규칙 id가 옛 판정에 남아 있어도 오류 없이 건너뛴다
    guide = contract_day_guide(["L-REMOVED", "L-MORTGAGE"], rules)
    assert [t.id for t in guide.terms] == ["S-NO-MORTGAGE"]
