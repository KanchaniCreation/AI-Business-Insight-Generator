import io
import json

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "")
    return TestClient(create_app(str(tmp_path / "api.db")))


@pytest.fixture
def csv_bytes(sample_raw_df):
    return sample_raw_df.to_csv(index=False).encode("utf-8")


def _upload(client, data, name="sales.csv", **form):
    return client.post("/datasets", files={"file": (name, io.BytesIO(data), "text/csv")}, data=form)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_full_flow_upload_analyze_insights_report(client, csv_bytes):
    up = _upload(client, csv_bytes)
    assert up.status_code == 201 and up.json()["rows_out"] < up.json()["rows_in"]
    did = up.json()["dataset_id"]
    run = client.post(f"/datasets/{did}/analyze", json={})
    assert run.status_code == 200 and run.json()["payload"]["kpis"]["revenue"]["current"] > 0
    rid = run.json()["run_id"]
    assert client.get(f"/runs/{rid}/report?format=md").status_code == 404          # not generated yet
    ins = client.post(f"/runs/{rid}/insights")
    assert ins.status_code == 200 and ins.json()["meta"]["source"] == "fallback"
    assert "Executive Summary" in client.get(f"/runs/{rid}/report?format=md").text
    docx = client.get(f"/runs/{rid}/report?format=docx")
    assert docx.status_code == 200 and docx.content[:2] == b"PK"                     # a .docx is a zip
    assert client.get(f"/runs/{rid}/report?format=json").json()["report"]["executive_summary"]
    assert client.get(f"/runs/{rid}/report?format=pdf").status_code == 422


def test_listing_and_deleting(client, csv_bytes):
    did = _upload(client, csv_bytes).json()["dataset_id"]
    assert client.get("/datasets").json()["datasets"][0]["id"] == did
    assert client.get(f"/datasets/{did}").json()["mapping"]["Sales"] == "Sales"
    assert client.delete(f"/datasets/{did}").status_code == 204
    assert client.get(f"/datasets/{did}").status_code == 404


def test_sql_endpoints(client, csv_bytes):
    did = _upload(client, csv_bytes).json()["dataset_id"]
    assert len(client.get(f"/datasets/{did}/monthly").json()["months"]) >= 2
    rows = client.get(f"/datasets/{did}/breakdown?dimension=Region").json()["rows"]
    assert abs(sum(r["contribution_pct"] for r in rows) - 100) < 0.1
    assert client.get(f"/datasets/{did}/breakdown?dimension=nope").status_code == 422


@pytest.mark.parametrize("data,name,fragment", [
    (b"", "x.csv", "empty"), (b"a,b\n1,2\n", "x.txt", "Unsupported"), (b"not excel", "x.xlsx", "Could not read"),
    (b"Foo,Bar\n1,2\n", "x.csv", "required")])
def test_bad_uploads_give_422_with_message(client, data, name, fragment):
    r = _upload(client, data, name)
    assert r.status_code == 422 and fragment.lower() in r.json()["error"].lower()


def test_invalid_mapping_json_and_currency(client, csv_bytes):
    assert _upload(client, csv_bytes, mapping="{not json").status_code == 422
    assert _upload(client, csv_bytes, currency="XYZ").status_code == 422


def test_custom_mapping_and_currency(client, superstore_raw):
    data = superstore_raw.to_csv(index=False).encode("utf-8")
    sug = client.post("/mapping/suggest", files={"file": ("s.csv", io.BytesIO(data), "text/csv")}).json()
    assert sug["problems"] == [] and sug["suggested_mapping"]["Date"] == "Order Date"
    up = _upload(client, data, mapping=json.dumps(sug["suggested_mapping"]), currency="USD")
    assert up.status_code == 201 and up.json()["date_format"].startswith("month-first")
    did = up.json()["dataset_id"]
    payload = client.post(f"/datasets/{did}/analyze", json={"period": None}).json()["payload"]
    assert payload["currency"] == "USD" and payload["kpis"]["revenue"]["current_display"].startswith("$")


def test_unknown_period_gives_clear_error(client, csv_bytes):
    did = _upload(client, csv_bytes).json()["dataset_id"]
    r = client.post(f"/datasets/{did}/analyze", json={"period": "2030-01"})
    assert r.status_code in (404, 422) and "2030-01" in r.json()["error"]


def test_api_key_protection(tmp_path, monkeypatch, csv_bytes):
    monkeypatch.setenv("API_KEY", "secret123")
    c = TestClient(create_app(str(tmp_path / "k.db")))
    assert c.get("/health").status_code == 200                                    # health stays public
    assert c.get("/datasets").status_code == 401
    assert c.get("/datasets", headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/datasets", headers={"X-API-Key": "secret123"}).status_code == 200
