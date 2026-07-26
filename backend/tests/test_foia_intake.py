"""
Tests for the FOIA-reply email-intake pipeline (app/foia_intake/).

Covers:
  * the parser's heuristic header -> canonical-field mapping across
    varied, realistic agency column names (CSV + XLSX);
  * unmapped-column preservation, synthetic permit numbers, cost/value
    mirroring, and graceful PDF failure;
  * sender -> FOIA-target resolution (exact + domain fallback);
  * end-to-end intake against a MOCKED Gmail service (no network), and the
    ProcessedEmailAttachment idempotency guard (re-running the poll does
    not re-ingest the same attachment).
"""
from __future__ import annotations

import base64
import io

from openpyxl import Workbook

from app.foia_intake import parser
from app.foia_intake.gmail_client import GmailClient, build_foia_search_query
from app.foia_intake.intake import poll_and_ingest
from app.foia_intake.targets import find_target_for_sender
from app.models import Jurisdiction, Permit, ProcessedEmailAttachment, SourceSystem


# ---------------------------------------------------------------------------
# Parser: heuristic field mapping
# ---------------------------------------------------------------------------


def test_field_mapping_varied_headers():
    headers = [
        "Permit No", "Permit Type", "Issued Date", "Site Address",
        "Estimated Cost", "Contractor Name", "Work Description", "APN", "Sq Ft",
    ]
    mapping = parser.build_field_mapping(headers)
    assert mapping["permit_number"] == "Permit No"
    assert mapping["permit_type"] == "Permit Type"
    assert mapping["issue_date"] == "Issued Date"
    assert mapping["property_address"] == "Site Address"
    assert mapping["estimated_cost"] == "Estimated Cost"
    assert mapping["contractor"] == "Contractor Name"
    assert mapping["description"] == "Work Description"
    assert mapping["parcel_number"] == "APN"
    assert mapping["square_footage"] == "Sq Ft"


def test_field_mapping_alternate_vocabulary():
    # A totally different agency's naming for the same concepts.
    headers = [
        "Application #", "Record Type", "Date Applied", "Date Issued",
        "Property Address", "Declared Valuation", "Applicant", "Parcel ID",
    ]
    mapping = parser.build_field_mapping(headers)
    assert mapping["permit_number"] == "Application #"
    assert mapping["permit_type"] == "Record Type"
    assert mapping["application_date"] == "Date Applied"
    assert mapping["issue_date"] == "Date Issued"
    assert mapping["property_address"] == "Property Address"
    assert mapping["valuation"] == "Declared Valuation"
    assert mapping["builder"] == "Applicant"
    assert mapping["parcel_number"] == "Parcel ID"


def test_short_token_not_falsely_matched():
    # "lat" as a bare token maps; embedded in another word it must not.
    assert parser.build_field_mapping(["Lat", "Lng"]).get("latitude") == "Lat"
    m = parser.build_field_mapping(["Plate Number", "Related Info"])
    assert "latitude" not in m
    assert "longitude" not in m


def test_parse_csv_maps_and_coerces_values():
    csv_bytes = (
        "Permit No,Issued Date,Site Address,Estimated Cost,Extra Notes\n"
        "BLD-2026-001,03/15/2026,123 Main St,\"$12,500\",keep me\n"
        "BLD-2026-002,2026-04-01,456 Oak Ave,7500,also keep\n"
    ).encode("utf-8")
    result = parser.parse_csv(csv_bytes, "foia_email:test:msg1")
    assert result.ok
    assert len(result.records) == 2

    r0 = result.records[0]
    assert r0["permit_number"] == "BLD-2026-001"
    assert r0["issue_date"].year == 2026 and r0["issue_date"].month == 3
    assert r0["property_address"] == "123 Main St"
    assert r0["estimated_cost"] == 12500.0
    # cost mirrored into valuation when only one side is present
    assert r0["valuation"] == 12500.0
    assert r0["needs_review"] is True
    # Unmapped column preserved verbatim in raw_data
    assert r0["raw_data"]["Extra Notes"] == "keep me"
    assert r0["source"] == "foia_email:test:msg1"


def test_parse_csv_synthesizes_permit_number_when_absent():
    csv_bytes = (
        "Address,Work Description,Value\n"
        "1 Elm St,New deck,5000\n"
    ).encode("utf-8")
    result = parser.parse_csv(csv_bytes, "foia_email:test:msgX")
    assert result.ok
    pn = result.records[0]["permit_number"]
    assert pn.startswith("FOIA-")
    # Deterministic: same row -> same synthetic id (idempotent re-parse)
    again = parser.parse_csv(csv_bytes, "foia_email:test:msgX")
    assert again.records[0]["permit_number"] == pn
    # value -> valuation, mirrored into estimated_cost
    assert result.records[0]["valuation"] == 5000.0
    assert result.records[0]["estimated_cost"] == 5000.0


def test_parse_csv_semicolon_delimiter():
    csv_bytes = b"Permit Number;Status;Address\nP1;Issued;9 Pine Rd\n"
    result = parser.parse_csv(csv_bytes, "foia_email:test:msgS")
    assert result.ok
    assert result.records[0]["permit_number"] == "P1"
    assert result.records[0]["status"] == "Issued"


def test_parse_xlsx():
    wb = Workbook()
    ws = wb.active
    ws.append(["Permit #", "Permit Type", "Date Issued", "Job Address", "Valuation"])
    ws.append(["X-1", "Residential", "2026-01-05", "500 State St", 250000])
    ws.append(["X-2", "Commercial", "2026-02-10", "600 Market St", 1000000])
    buf = io.BytesIO()
    wb.save(buf)

    result = parser.parse_xlsx(buf.getvalue(), "foia_email:test:xlsx")
    assert result.ok
    assert len(result.records) == 2
    assert result.records[0]["permit_number"] == "X-1"
    assert result.records[0]["valuation"] == 250000.0
    assert result.records[1]["property_address"] == "600 Market St"


def test_parse_pdf_without_table_fails_gracefully():
    # Not a real PDF at all -> must fail gracefully, not raise.
    result = parser.parse_pdf(b"this is not a pdf", "foia_email:test:pdf")
    assert result.status == "unparseable"
    assert result.records == []


def test_parse_attachment_dispatch_and_legacy_xls():
    # magic-byte sniffing for a mislabeled attachment
    wb = Workbook()
    wb.active.append(["Permit No", "Address"])
    wb.active.append(["A", "1 St"])
    buf = io.BytesIO()
    wb.save(buf)
    res = parser.parse_attachment("data.bin", buf.getvalue(), "foia_email:test:x")
    assert res.ok  # sniffed the PK zip header -> xlsx

    legacy = parser.parse_attachment("old.xls", b"\xd0\xcf\x11\xe0garbage", "foia_email:test:x")
    assert legacy.status == "unsupported"


def test_parse_email_body_inline_table():
    body = "Permit No | Address | Value\nP-9 | 12 Bay St | 4000\nP-10 | 34 Bay St | 8000\n"
    result = parser.parse_email_body(body, "foia_email:test:body")
    assert result.ok
    assert result.records[0]["permit_number"] == "P-9"


def test_parse_email_body_prose_is_not_data():
    body = "Hello,\n\nPlease find our response to your request attached.\n\nRegards,\nRecords Officer"
    result = parser.parse_email_body(body, "foia_email:test:body")
    assert result.status == "no_records"


# ---------------------------------------------------------------------------
# Target resolution + query building
# ---------------------------------------------------------------------------


def test_find_target_exact_and_domain_fallback():
    assert find_target_for_sender("permits@huntingtonwv.gov").key == "huntington_wv"
    # domain fallback: records officer replies from a personal mailbox
    assert find_target_for_sender("Jane Doe <jane.doe@huntingtonwv.gov>").key == "huntington_wv"
    assert find_target_for_sender("someone@unrelated.com") is None


def test_build_search_query():
    q = build_foia_search_query(["a@x.gov", "b@y.gov"])
    assert "from:(a@x.gov OR b@y.gov)" in q
    assert "-in:sent" in q


# ---------------------------------------------------------------------------
# End-to-end intake with a MOCKED Gmail service + idempotency
# ---------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


class _FakeExec:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class _FakeAttachments:
    def __init__(self, store):
        self._store = store

    def get(self, userId, messageId, id):
        return _FakeExec({"data": self._store[id]})


class _FakeMessages:
    def __init__(self, listing, messages, attachments):
        self._listing = listing
        self._messages = messages
        self._attachments = attachments

    def list(self, userId, q, maxResults, pageToken=None):
        return _FakeExec(self._listing)

    def get(self, userId, id, format):
        return _FakeExec(self._messages[id])

    def attachments(self):
        return _FakeAttachments(self._attachments)


class _FakeUsers:
    def __init__(self, messages, profile_email):
        self._messages = messages
        self._profile_email = profile_email

    def messages(self):
        return self._messages

    def getProfile(self, userId):
        return _FakeExec({"emailAddress": self._profile_email})


class _FakeService:
    def __init__(self, users):
        self._users = users

    def users(self):
        return self._users


def _make_client_with_csv(csv_bytes: bytes, from_addr: str, filename="permits.csv"):
    attachment_id = "att-1"
    message = {
        "id": "msg-1",
        "threadId": "thread-1",
        "snippet": "Response attached",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "Subject", "value": "RE: FOIA Request"},
                {"name": "Date", "value": "Mon, 27 Jul 2026 10:00:00 -0500"},
            ],
            "parts": [
                {"partId": "0", "mimeType": "text/plain",
                 "body": {"data": _b64url(b"Please see attached.")}},
                {"partId": "1", "mimeType": "text/csv", "filename": filename,
                 "body": {"attachmentId": attachment_id, "size": len(csv_bytes)}},
            ],
        },
    }
    users = _FakeUsers(
        _FakeMessages(
            listing={"messages": [{"id": "msg-1"}]},
            messages={"msg-1": message},
            attachments={attachment_id: _b64url(csv_bytes)},
        ),
        profile_email="permitbuildadscharf@gmail.com",
    )
    return GmailClient(service=_FakeService(users))


def test_gmail_client_parses_envelope_and_downloads(db_session):
    csv_bytes = b"Permit No,Issued Date,Site Address,Estimated Cost\nH-1,2026-05-01,10 River Rd,20000\n"
    client = _make_client_with_csv(csv_bytes, "permits@huntingtonwv.gov")
    assert client.get_profile_email() == "permitbuildadscharf@gmail.com"
    ids = client.list_message_ids("whatever")
    assert ids == ["msg-1"]
    msg = client.get_message("msg-1")
    assert msg.from_address == "permits@huntingtonwv.gov"
    assert "Please see attached." in msg.body_text
    assert len(msg.attachments) == 1
    assert client.download_attachment("msg-1", msg.attachments[0].attachment_id) == csv_bytes


def test_end_to_end_intake_and_idempotency(db_session):
    csv_bytes = (
        b"Permit No,Issued Date,Site Address,Estimated Cost,Weird Column\n"
        b"H-1,2026-05-01,10 River Rd,20000,foo\n"
        b"H-2,2026-05-02,12 River Rd,35000,bar\n"
    )
    client = _make_client_with_csv(csv_bytes, "permits@huntingtonwv.gov")

    stats = poll_and_ingest(db_session, client=client, geocode_missing=False, enrich=False)
    assert stats.records_created == 2
    assert stats.records_flagged == 2
    assert stats.errors == 0

    # Jurisdiction was created with the FOIA_EMAIL source system.
    jur = (
        db_session.query(Jurisdiction)
        .filter(Jurisdiction.name == "Huntington", Jurisdiction.state == "WV")
        .one()
    )
    assert jur.source_system == SourceSystem.FOIA_EMAIL

    permits = db_session.query(Permit).filter(Permit.jurisdiction_id == jur.id).all()
    assert len(permits) == 2
    assert all(p.needs_review for p in permits)
    h1 = next(p for p in permits if p.permit_number == "H-1")
    assert h1.estimated_cost == 20000.0
    assert h1.raw_data["Weird Column"] == "foo"  # unmapped column preserved

    # Ledger recorded the attachment.
    ledger = db_session.query(ProcessedEmailAttachment).all()
    assert any(pea.attachment_id == "att-1" and pea.records_created == 2 for pea in ledger)

    # --- second run must be a no-op (idempotent) ---
    client2 = _make_client_with_csv(csv_bytes, "permits@huntingtonwv.gov")
    stats2 = poll_and_ingest(db_session, client=client2, geocode_missing=False, enrich=False)
    assert stats2.records_created == 0
    assert stats2.attachments_skipped >= 1
    # No duplicate permits created.
    assert db_session.query(Permit).filter(Permit.jurisdiction_id == jur.id).count() == 2
