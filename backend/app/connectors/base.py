"""
Abstract interface every permit-data connector implements.

New jurisdictions/vendors plug in by subclassing PermitConnector and
implementing discover()/fetch_permits(); the ingest router
(app/routers/ingest.py) and CLI script (scripts/run_ingest.py) work
against this interface only, never against a specific vendor's SDK/shape.

All connectors return a list of *normalized* dicts whose keys line up
1:1 with app.models.Permit's mappable columns (permit_number,
permit_type, status, application_date, issue_date, ..., raw_data).
Field mapping from a source's native column names into this shape is
each connector's job (see socrata.py / arcgis.py "mapping config"
pattern), so the rest of the app never has to know about
source-specific quirks.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

# The canonical set of keys a connector should populate on each permit
# dict it yields. Not every source will have every field -- missing
# ones should simply be omitted / None, never fabricated.
NORMALIZED_PERMIT_FIELDS = (
    "permit_number",
    "permit_type",
    "status",
    "application_date",
    "issue_date",
    "completion_date",
    "expiration_date",
    "contractor",
    "builder",
    "architect",
    "engineer",
    "property_address",
    "parcel_number",
    "estimated_cost",
    "valuation",
    "description",
    "work_category",
    "square_footage",
    "units",
    "latitude",
    "longitude",
    "permit_url",
    "source",
    "raw_data",
)


@dataclass
class ConnectorInfo:
    """Metadata describing a connector instance, returned by discover()."""

    source_system: str  # "socrata" | "arcgis"
    identifier: str  # domain+dataset id, or service URL
    display_name: str
    record_count: Optional[int] = None
    fields: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


class PermitConnector(abc.ABC):
    """
    Abstract base for all permit-data source connectors.

    Subclasses are constructed with whatever source-specific config
    they need (a Socrata domain+dataset id, an ArcGIS service URL,
    etc.) plus a field-mapping config, and expose only these two
    methods to the rest of the application.
    """

    #: short machine-readable name, e.g. "socrata" or "arcgis"
    source_system: str = "unknown"

    @abc.abstractmethod
    def discover(self) -> ConnectorInfo:
        """
        Probe the live source (metadata endpoint) and return basic info
        about it -- used to sanity-check a new jurisdiction config
        before running a full ingest, and by `scripts/run_ingest.py
        --discover-only`.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_permits(self, since: Optional[datetime] = None, limit: Optional[int] = None) -> Iterable[dict]:
        """
        Fetch permits from the live source, normalize each record into
        the NORMALIZED_PERMIT_FIELDS shape, and yield them.

        Args:
            since: only fetch records updated/created on or after this
                timestamp, if the source supports incremental filtering.
                Connectors that can't filter server-side may fetch more
                and filter client-side, or ignore it and rely on the
                ingest upsert logic to no-op unchanged rows.
            limit: cap on the number of records to fetch (mainly for
                demos/tests against live endpoints without hammering them).
        """
        raise NotImplementedError

    def normalized_stub(self) -> dict:
        """Helper: an empty normalized-permit dict with all keys present."""
        return {k: None for k in NORMALIZED_PERMIT_FIELDS}
