"""첫 계약 서류 올리기·보기·삭제 (POST /api/contracts/{id}/documents, GET·DELETE .../documents/{kind}, FR-051·033, #46)."""
import pytest

from app import evidence
from tests.test_contract_patch import _contract

PHOTO = b"\xff\xd8\xff\xe0 fake jpeg"


@pytest.fixture(autouse=True)
def evidence_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "evidence"))
    return tmp_path / "evidence"


def _h(c: dict) -> dict:
    return {"X-Contract-Token": c["access_token"]}


def _upload(client, c: dict, kind: str, data: bytes = PHOTO, name: str = "photo.jpg"):
    return client.post(f"/api/contracts/{c['id']}/documents", data={"kind": kind},
                       files={"file": (name, data, "image/jpeg")}, headers=_h(c))


def _docs(body: dict) -> dict:
    return {d["kind"]: d for d in body["documents"]}


def test_contract_lists_document_kinds(client):
    c = _contract(client)
    docs = _docs(c)
    assert list(docs) == ["contract", "down_payment"]
    assert docs["contract"]["label"] == "계약서" and docs["down_payment"]["label"] == "계약금 이체 내역"
    assert not any(d["uploaded"] or d["uploaded_at"] for d in docs.values())


def test_upload_view_replace_delete(client, evidence_tmp):
    c = _contract(client)
    r = _upload(client, c, "contract")
    assert r.status_code == 200, r.text
    docs = _docs(r.json())
    assert docs["contract"]["uploaded"] and docs["contract"]["uploaded_at"] and not docs["down_payment"]["uploaded"]
    # 할 일은 바뀌지 않는다 (할 일 증빙이 아니라 기록함의 첫 서류)
    assert [(t["rule_id"], t["status"]) for t in r.json()["todos"]] == [(t["rule_id"], t["status"]) for t in c["todos"]]

    r = client.get(f"/api/contracts/{c['id']}/documents/contract", headers=_h(c))
    assert r.status_code == 200 and r.content == PHOTO
    assert r.headers["content-type"] == "image/jpeg" and r.headers["content-disposition"].startswith("inline")

    # 다시 올리면 바꾼다 (파일은 하나만 남음). SVG는 내려받기로
    assert _upload(client, c, "contract", b"<svg/>", "x.svg").status_code == 200
    files = list(evidence_tmp.rglob("*.*"))
    assert len(files) == 1 and files[0].suffix == ".svg"
    r = client.get(f"/api/contracts/{c['id']}/documents/contract", headers=_h(c))
    assert r.headers["content-disposition"].startswith("attachment")

    r = client.delete(f"/api/contracts/{c['id']}/documents/contract", headers=_h(c))
    assert r.status_code == 200 and not _docs(r.json())["contract"]["uploaded"]
    assert list(evidence_tmp.rglob("*.*")) == []
    assert client.get(f"/api/contracts/{c['id']}/documents/contract", headers=_h(c)).status_code == 404
    assert client.delete(f"/api/contracts/{c['id']}/documents/contract", headers=_h(c)).status_code == 404


def test_invalid_uploads(client, monkeypatch):
    c = _contract(client)
    r = _upload(client, c, "lease")
    assert r.status_code == 422 and "kind" in r.text
    assert _upload(client, c, "contract", b"").status_code == 422
    monkeypatch.setattr(evidence, "MAX_EVIDENCE_BYTES", 5)
    r = _upload(client, c, "down_payment")
    assert r.status_code == 413 and r.json()["detail"]["code"] == "FILE_TOO_LARGE"
    assert client.get(f"/api/contracts/{c['id']}/documents/lease", headers=_h(c)).status_code == 404


def test_token_and_cancelled_contract(client):
    c = _contract(client)
    assert _upload(client, c, "contract").status_code == 200
    wrong = {"X-Contract-Token": "wrong"}
    assert client.get(f"/api/contracts/{c['id']}/documents/contract", headers=wrong).status_code == 404
    r = client.post(f"/api/contracts/{c['id']}/documents", data={"kind": "contract"},
                    files={"file": ("p.jpg", PHOTO, "image/jpeg")}, headers=wrong)
    assert r.status_code == 404

    assert client.post(f"/api/contracts/{c['id']}/cancel", headers=_h(c)).status_code == 200
    r = _upload(client, c, "down_payment")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CONTRACT_CANCELLED"
    # 무산된 계약도 보기·삭제는 된다 (FR-016, FR-033)
    assert client.get(f"/api/contracts/{c['id']}/documents/contract", headers=_h(c)).status_code == 200
    assert client.delete(f"/api/contracts/{c['id']}/documents/contract", headers=_h(c)).status_code == 200
