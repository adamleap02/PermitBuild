"""
Thin wrapper over the Gmail API for the FOIA-reply intake pipeline.

Uses the saved OAuth token at backend/gmail_token.json (created once by
scripts/gmail_oauth_setup.py -- gmail.send + gmail.readonly scopes for
permitbuildadscharf@gmail.com). readonly is all this client needs: it
lists/reads messages and downloads attachments, and never modifies or
deletes anything in the mailbox.

Everything here is a plain, well-typed dataclass return so the rest of
the pipeline (and its tests) never has to deal with the raw Gmail JSON
envelope, and so the Gmail service object is the single thing tests need
to mock.
"""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

DEFAULT_TOKEN_PATH = str(Path(__file__).resolve().parent.parent.parent / "gmail_token.json")


@dataclass
class EmailAttachment:
    """One attachment part on a message (metadata only until fetched)."""

    attachment_id: str
    part_id: str
    filename: str
    mime_type: str
    size: Optional[int] = None


@dataclass
class EmailMessage:
    message_id: str
    thread_id: str
    from_address: str
    subject: str
    date: str
    snippet: str
    body_text: str = ""
    attachments: list[EmailAttachment] = field(default_factory=list)


class GmailAuthError(RuntimeError):
    """Raised when the saved token is missing/invalid and cannot be used."""


class GmailClient:
    """
    Read-only Gmail access for FOIA-reply intake.

    Construct with the default saved token, or inject a pre-built Gmail
    `service` object (that's how the tests drive it without any network).
    """

    def __init__(self, service: Any = None, token_path: str = DEFAULT_TOKEN_PATH, user_id: str = "me"):
        self.user_id = user_id
        self._service = service
        self._token_path = token_path

    # -- construction ------------------------------------------------------

    @property
    def service(self) -> Any:
        if self._service is None:
            self._service = self._build_service()
        return self._service

    def _build_service(self) -> Any:
        # Imported lazily so importing this module (and running the parser
        # tests) never requires the Google libraries to be present.
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        if not os.path.exists(self._token_path):
            raise GmailAuthError(
                f"Gmail token not found at {self._token_path}. Run "
                "scripts/gmail_oauth_setup.py (needs a human to click through "
                "the browser consent screen once) before polling."
            )
        creds = Credentials.from_authorized_user_file(self._token_path, SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Persist the refreshed access token so the next scheduled
                # run doesn't have to refresh again.
                try:
                    with open(self._token_path, "w") as fh:
                        fh.write(creds.to_json())
                except OSError:
                    logger.warning("Could not persist refreshed Gmail token", exc_info=True)
            else:
                raise GmailAuthError(
                    "Saved Gmail token is invalid and cannot be refreshed. "
                    "Re-run scripts/gmail_oauth_setup.py."
                )
        return build("gmail", "v1", credentials=creds)

    # -- reads -------------------------------------------------------------

    def get_profile_email(self) -> str:
        """Return the authorized account's address (cheap connectivity check)."""
        profile = self.service.users().getProfile(userId=self.user_id).execute()
        return profile.get("emailAddress", "")

    def list_message_ids(self, query: str, max_results: int = 100) -> list[str]:
        """List message ids matching a Gmail search query, paging through results."""
        ids: list[str] = []
        page_token: Optional[str] = None
        while True:
            resp = (
                self.service.users()
                .messages()
                .list(userId=self.user_id, q=query, maxResults=min(100, max_results), pageToken=page_token)
                .execute()
            )
            for m in resp.get("messages", []):
                ids.append(m["id"])
                if len(ids) >= max_results:
                    return ids
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return ids

    def get_message(self, message_id: str) -> EmailMessage:
        """Fetch a full message and flatten it into an EmailMessage."""
        raw = (
            self.service.users()
            .messages()
            .get(userId=self.user_id, id=message_id, format="full")
            .execute()
        )
        payload = raw.get("payload", {}) or {}
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

        body_parts: list[str] = []
        attachments: list[EmailAttachment] = []
        _walk_parts(payload, body_parts, attachments)

        return EmailMessage(
            message_id=raw.get("id", message_id),
            thread_id=raw.get("threadId", ""),
            from_address=headers.get("from", ""),
            subject=headers.get("subject", ""),
            date=headers.get("date", ""),
            snippet=raw.get("snippet", ""),
            body_text="\n".join(p for p in body_parts if p),
            attachments=attachments,
        )

    def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download and base64url-decode a single attachment's bytes."""
        att = (
            self.service.users()
            .messages()
            .attachments()
            .get(userId=self.user_id, messageId=message_id, id=attachment_id)
            .execute()
        )
        data = att.get("data", "")
        return _b64url_decode(data)


def _walk_parts(part: dict, body_parts: list[str], attachments: list[EmailAttachment]) -> None:
    """Recursively collect text/plain body chunks and attachment metadata."""
    mime = part.get("mimeType", "") or ""
    filename = part.get("filename", "") or ""
    body = part.get("body", {}) or {}

    if filename and body.get("attachmentId"):
        attachments.append(
            EmailAttachment(
                attachment_id=body["attachmentId"],
                part_id=part.get("partId", ""),
                filename=filename,
                mime_type=mime,
                size=body.get("size"),
            )
        )
    elif mime == "text/plain" and body.get("data"):
        try:
            body_parts.append(_b64url_decode(body["data"]).decode("utf-8", errors="replace"))
        except Exception:  # pragma: no cover - defensive
            logger.debug("Failed to decode text/plain body part", exc_info=True)

    for sub in part.get("parts", []) or []:
        _walk_parts(sub, body_parts, attachments)


def _b64url_decode(data: str) -> bytes:
    # Gmail returns base64url with padding sometimes stripped.
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def build_foia_search_query(emails: list[str]) -> str:
    """
    Build the Gmail search query for FOIA replies.

    ``from:(a@x OR b@y OR ...)`` restricted to received mail (not our own
    sent copies). Domain fallbacks are added as ``from:@domain`` terms so a
    records officer replying from a personal mailbox on the agency domain
    is still caught; final sender->target resolution is done precisely in
    targets.find_target_for_sender().
    """
    parts = [e for e in emails if e]
    if not parts:
        return "in:inbox"
    joined = " OR ".join(parts)
    return f"from:({joined}) -in:sent"
