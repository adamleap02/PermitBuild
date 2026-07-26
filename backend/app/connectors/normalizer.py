"""
Address normalization.

Implements a basic, dependency-free USPS-style standardizer: expands
common abbreviations to a canonical short form (St -> ST, Avenue ->
AVE), standardizes directionals (North -> N), and standardizes unit
designators (Apartment -> APT, Suite -> STE). This is NOT USPS
CASS-certified validation -- it is a local, rules/regex-based cleanup
so addresses from different jurisdictions compare/match reasonably
well (e.g. for de-duplicating properties across permits).

For real deliverability validation/standardization, USPS provides a
free (registration-required) Web Tools API -- see BLOCKERS.md for the
registration link and what integrating it would add on top of this.
"""
from __future__ import annotations

import re

# Ordered so longer/more specific tokens are replaced before shorter
# ones that could be substrings (e.g. "STREET" before "ST").
_STREET_SUFFIXES: dict[str, str] = {
    "ALLEY": "ALY",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "CIRCLE": "CIR",
    "COURT": "CT",
    "CRESCENT": "CRES",
    "DRIVE": "DR",
    "EXPRESSWAY": "EXPY",
    "FREEWAY": "FWY",
    "HIGHWAY": "HWY",
    "HEIGHTS": "HTS",
    "ISLAND": "IS",
    "JUNCTION": "JCT",
    "LANE": "LN",
    "LOOP": "LOOP",
    "MOUNTAIN": "MTN",
    "PARKWAY": "PKWY",
    "PLACE": "PL",
    "PLAZA": "PLZ",
    "POINT": "PT",
    "ROAD": "RD",
    "SQUARE": "SQ",
    "STREET": "ST",
    "TERRACE": "TER",
    "TRAIL": "TRL",
    "TURNPIKE": "TPKE",
    "WAY": "WAY",
}

_DIRECTIONALS: dict[str, str] = {
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
}

_UNIT_DESIGNATORS: dict[str, str] = {
    "APARTMENT": "APT",
    "BUILDING": "BLDG",
    "BASEMENT": "BSMT",
    "DEPARTMENT": "DEPT",
    "FLOOR": "FL",
    "HANGAR": "HNGR",
    "LOT": "LOT",
    "LOWER": "LOWR",
    "OFFICE": "OFC",
    "PENTHOUSE": "PH",
    "PIER": "PIER",
    "ROOM": "RM",
    "SPACE": "SPC",
    "SUITE": "STE",
    "TRAILER": "TRLR",
    "UNIT": "UNIT",
    "UPPER": "UPPR",
}

# Ordinal-suffixed street numbers (1ST, 2ND, ...) should never be
# swallowed by the suffix/directional maps -- handled implicitly since
# those tokens aren't in the maps above.

_ALL_TOKEN_MAP: dict[str, str] = {**_STREET_SUFFIXES, **_DIRECTIONALS, **_UNIT_DESIGNATORS}

_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^\w\s#&/-]")


def normalize_address(raw_address: str | None) -> str | None:
    """
    Return a standardized, upper-cased, single-line address string.

    Examples
    --------
    >>> normalize_address("930 sutter street")
    '930 SUTTER ST'
    >>> normalize_address("1245 North Miller Road, Apartment 4")
    '1245 N MILLER RD APT 4'
    """
    if raw_address is None:
        return None
    text = raw_address.strip()
    if not text:
        return None

    text = text.upper()
    text = text.replace(",", " ")
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()

    tokens = text.split(" ")
    normalized_tokens = [_ALL_TOKEN_MAP.get(tok, tok) for tok in tokens]
    result = " ".join(normalized_tokens)
    result = _WHITESPACE_RE.sub(" ", result).strip()
    return result


def split_address_components(raw_address: str | None) -> dict[str, str | None]:
    """
    Best-effort split of a US address into street/city/state/zip when
    the input follows a "STREET, CITY, STATE ZIP" convention (common
    in permit datasets that only give one address field). Returns Nones
    for parts it can't confidently find rather than guessing.
    """
    result: dict[str, str | None] = {"street": None, "city": None, "state": None, "zip_code": None}
    if not raw_address:
        return result

    zip_match = re.search(r"(\d{5})(?:-\d{4})?\s*$", raw_address)
    remainder = raw_address
    if zip_match:
        result["zip_code"] = zip_match.group(1)
        remainder = raw_address[: zip_match.start()].strip().rstrip(",")

    state_match = re.search(r",\s*([A-Za-z]{2})\s*$", remainder)
    if state_match:
        result["state"] = state_match.group(1).upper()
        remainder = remainder[: state_match.start()].strip().rstrip(",")

    parts = [p.strip() for p in remainder.split(",") if p.strip()]
    if len(parts) >= 2:
        result["street"] = parts[0]
        result["city"] = parts[1]
    elif len(parts) == 1:
        result["street"] = parts[0]

    return result


def build_full_address(
    street_number: str | None,
    street_direction: str | None,
    street_name: str | None,
    street_suffix: str | None,
    unit: str | None = None,
    city: str | None = None,
    state: str | None = None,
    zip_code: str | None = None,
) -> str | None:
    """Assemble + normalize an address from its component parts (many
    permit datasets, e.g. SF/Tempe, provide these separately rather
    than as one combined field)."""
    street_parts = [street_number, street_direction, street_name, street_suffix]
    street = " ".join(p for p in street_parts if p)
    if unit:
        street = f"{street} {unit}"
    if not street.strip():
        return None

    tail_parts = [city, state]
    tail = " ".join(p for p in tail_parts if p)
    full = street
    if tail:
        full = f"{full}, {tail}"
    if zip_code:
        full = f"{full} {zip_code}"

    return normalize_address(full)
