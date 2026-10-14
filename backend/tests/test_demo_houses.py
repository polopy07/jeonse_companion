"""시연 집 2채 API (GET /api/demo-houses)와 경보 계산 정답표(docs/validation/demo_houses.yaml) 대조."""
import yaml

from app.config import REPO_ROOT
from load_demo_trades import load as load_saved_trades

ANSWERS = {h["id"]: h for h in yaml.safe_load(
    (REPO_ROOT / "docs" / "validation" / "demo_houses.yaml").read_text(encoding="utf-8"))["houses"]}


def test_demo_houses(client):
    r = client.get("/api/demo-houses")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["as_of"] == "2026-10-13"
    houses = {h["id"]: h for h in body["houses"]}
    assert set(houses) == {"demo-apartment", "demo-villa"}

    villa = houses["demo-villa"]
    assert villa["input"]["complex"] == {"lawd_cd": "26500", "umd_name": "광안동", "complex_name": "제이제이", "jibun": "129-46"}
    # 시연 등기부는 POST /api/registry/parse와 같은 형식, 읽은 값이 정답표 입력과 같다
    assert villa["registry"]["owners"] == ["한가상"]
    assert [(m["rank"], m["amount"]) for m in villa["registry"]["mortgages"]] == [("5", 14_400_000)]
    assert {k: villa["registry"]["fields"][k] for k in villa["input"]["registry"]} == villa["input"]["registry"]
    assert villa["virtual"]   # 시연용 가상 근저당 (화면에 표시)
    assert villa["contract_day"]["special_term_result"] == {"S-NO-MORTGAGE": "rejected", "S-GUARANTEE-CANCEL": "inserted"}

    apt = houses["demo-apartment"]
    assert apt["registry"]["mortgages"] == [] and apt["virtual"] == [] and apt["contract_day"] is None


def test_demo_houses_match_answer_sheet(client):
    # API가 돌려준 입력으로 판정·계약을 만들면 정답표 기대값과 같아야 한다 (NFR-004)
    body = client.get("/api/demo-houses").json()
    as_of, added = load_saved_trades()
    assert as_of == body["as_of"] and added == 180

    for house in body["houses"]:
        exp = ANSWERS[house["id"]]["expected"]
        r = client.post("/api/checks", json=house["input"], headers={"X-Virtual-Today": as_of})
        assert r.status_code == 201, r.text
        check = r.json()
        assert check["level"] == exp["verdict"], house["id"]
        assert check["estimated_price"] == exp["estimated_price"], house["id"]
        assert round(check["deposit_ratio"], 4) == exp["deposit_ratio"], house["id"]
        assert [m["id"] for m in check["matched"]] == exp["matched"], house["id"]
        assert check["linkages"] == exp["linkages"], house["id"]
        assert check["trade_basis"] == exp["trade_basis"], house["id"]
        assert check["nearby_jeonse"] == exp["nearby_jeonse"], house["id"]

        # 경보 단계는 계약을 만들 때 정해진다. 계약 당일 장면이 없는 집은 같은 날짜로 특약 없이
        day = house["contract_day"] or {**ANSWERS["demo-villa"]["contract_day"]["dates"], "special_term_result": {}}
        r = client.post("/api/contracts", json={"check_id": check["id"], **day})
        assert r.status_code == 201, r.text
        contract = r.json()
        assert contract["alert_level"] == exp["alert_level"], house["id"]

        scene = ANSWERS[house["id"]].get("contract_day")
        if scene:
            todos = {t["rule_id"]: t for t in contract["todos"]}
            assert contract["todos"][0]["rule_id"] == scene["expected"]["top"]
            assert todos["T2"]["due_date"] == scene["expected"]["T2_due"]
            assert scene["expected"]["T3_required_check"] in todos["T3"]["required_checks"]
