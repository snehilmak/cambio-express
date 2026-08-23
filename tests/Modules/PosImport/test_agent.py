"""PosImport site-agent flow (P1-9 PR3): keys, staging, commit.

The invariants under test:

  * agent keys: issued once in plaintext, listed masked, revoked
    keys stop authenticating (opaque 401),
  * upload staging is idempotent per filename and records the
    business date; unparseable files stage with the error,
  * staged-days listing counts files + errors and flags committed
    days,
  * committing a staged day books DayClose closes through the
    same mapping gate as manual uploads,
  * employees cannot manage keys or staged commits (403).
"""
import base64

from tests.Modules.PosImport.test_ingest import (
    _mk_department, _map_codes, _outside_fuel_sale,
)
from tests.Modules.PosImport.test_naxml import _sale
from tests.conftest import login_admin, make_employee_client


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, test_store_id):
    return _headers(login_admin(client, test_store_id))


def _issue_key(client, h, label="Back office PC"):
    resp = client.post("/api/v2/posimport/agent-keys", headers=h,
                       json={"label": label})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _agent_upload(client, key, filename, doc):
    return client.post(
        "/api/v2/posimport/agent/upload",
        headers={"X-Agent-Key": key},
        json={
            "filename": filename,
            "content_base64": base64.b64encode(
                doc.encode("ISO-8859-1"),
            ).decode(),
        },
    )


def test_key_lifecycle_and_auth(client, test_store_id):
    h = _admin(client, test_store_id)
    issued = _issue_key(client, h)
    assert issued["key"].startswith("pak_")

    listed = client.get(
        "/api/v2/posimport/agent-keys", headers=h,
    ).json()["keys"]
    assert len(listed) == 1
    assert listed[0]["revoked"] is False
    # The raw key never comes back from the list.
    assert "key" not in listed[0]

    # Bad key → opaque 401.
    resp = _agent_upload(client, "pak_wrong", "PJR1.xml", _sale())
    assert resp.status_code == 401

    # Good key works, and stamps the heartbeat.
    resp = _agent_upload(client, issued["key"], "PJR1.xml", _sale())
    assert resp.status_code == 200, resp.text
    listed = client.get(
        "/api/v2/posimport/agent-keys", headers=h,
    ).json()["keys"]
    assert listed[0]["last_used_at"] is not None

    # Revoked key stops authenticating.
    resp = client.post(
        f"/api/v2/posimport/agent-keys/{issued['id']}/revoke", headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["keys"][0]["revoked"] is True
    resp = _agent_upload(client, issued["key"], "PJR2.xml", _sale())
    assert resp.status_code == 401


def test_upload_staging_idempotent_and_error_capture(
    client, test_store_id,
):
    h = _admin(client, test_store_id)
    key = _issue_key(client, h)["key"]

    resp = _agent_upload(client, key, "PJR0001.xml", _sale())
    body = resp.json()
    assert body["staged"] is True
    assert body["duplicate"] is False
    assert body["business_date"] == "2024-10-14"

    # Same filename again → duplicate, not re-staged.
    body = _agent_upload(client, key, "PJR0001.xml", _sale()).json()
    assert body["duplicate"] is True

    # Garbage stages WITH the error recorded (re-parse later).
    body = _agent_upload(client, key, "PJR0002.xml", "not xml").json()
    assert body["staged"] is True
    assert body["parse_error"] != ""
    assert body["business_date"] is None


def test_staged_days_and_commit(client, test_store_id):
    h = _admin(client, test_store_id)
    key = _issue_key(client, h)["key"]

    _agent_upload(client, key, "PJR0001.xml", _sale())
    _agent_upload(client, key, "PJR0002.xml", _outside_fuel_sale())
    _agent_upload(client, key, "PJRBAD.xml", "garbage")

    days = client.get(
        "/api/v2/posimport/staged", headers=h,
    ).json()["days"]
    assert days == [{
        "business_date": "2024-10-14", "file_count": 2,
        "error_count": 0, "committed": False,
    }]

    # Commit gate: unmapped codes block, then mapping unblocks.
    resp = client.post("/api/v2/posimport/staged/commit", headers=h,
                       json={"day": "2024-10-14"})
    assert resp.status_code == 422
    misc = _mk_department(client, h, "Misc")
    fuel = _mk_department(client, h, "Fuel")
    _map_codes(client, h, {"17": misc["id"], "1024": fuel["id"]})

    resp = client.post("/api/v2/posimport/staged/commit", headers=h,
                       json={"day": "2024-10-14"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["closes_written"] == 2

    days = client.get(
        "/api/v2/posimport/staged", headers=h,
    ).json()["days"]
    assert days[0]["committed"] is True

    day = client.get(
        "/api/v2/dayclose/day/2024-10-14", headers=h,
    ).json()
    assert {c["register_label"] for c in day["closes"]} == {
        "Register 1", "Pay at pump",
    }
    assert all(c["source"] == "gilbarco" for c in day["closes"])


def test_employee_denied_key_and_staged_surfaces(client, test_store_id):
    emp_client, emp_jwt = make_employee_client(test_store_id)
    emp_h = _headers(emp_jwt)
    assert client.post(
        "/api/v2/posimport/agent-keys", headers=emp_h, json={"label": "x"},
    ).status_code == 403
    assert client.get(
        "/api/v2/posimport/staged", headers=emp_h,
    ).status_code == 403
