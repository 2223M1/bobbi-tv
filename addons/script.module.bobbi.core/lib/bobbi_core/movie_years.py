"""Movie release years proved by one matching TMDb detail response.

Only the first global premiere, limited theatrical release and theatrical
release may supplement the primary date. Later releases and release windows
are not identity evidence. Instances stay in process; JSON dictionaries are
never accepted in their place.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Tuple


PROVENANCE = "tmdb.movie.details.release_dates.v1"
MAX_COUNTRIES = 256
MAX_RELEASE_ROWS = 4096
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?"
)


@dataclass(frozen=True)
class MovieYears:
    tmdb_id: int
    primary_year: int
    years: Tuple[int, ...]
    provenance: str = PROVENANCE


def _year(value):
    if type(value) is str and re.fullmatch(r"[0-9]{4}", value):
        value = int(value)
    return value if type(value) is int and 1000 <= value <= 9999 else None


def _date(value, timestamp=False):
    if type(value) is not str or len(value) > 32:
        return None
    try:
        if _DATE.fullmatch(value):
            result = date.fromisoformat(value)
        elif timestamp and _TIMESTAMP.fullmatch(value):
            result = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        else:
            return None
    except ValueError:
        return None
    return result if _year(result.year) is not None else None


def _has_error(value):
    return "error" in value or "errors" in value or value.get("success") is False


def _first_release_dates(optional):
    """Return per-type minima, or no optional evidence for malformed payloads."""
    if type(optional) is not dict or _has_error(optional):
        return {}
    countries = optional.get("results")
    if type(countries) is not list or len(countries) > MAX_COUNTRIES:
        return {}
    first = {}
    count = 0
    for country in countries:
        if type(country) is not dict or _has_error(country):
            return {}
        rows = country.get("release_dates")
        if type(rows) is not list:
            return {}
        count += len(rows)
        if count > MAX_RELEASE_ROWS:
            # A truncated scan cannot establish the global first release.
            return {}
        for row in rows:
            if type(row) is not dict or _has_error(row):
                return {}
            release_type = row.get("type")
            if type(release_type) is not int or release_type not in (1, 2, 3, 4, 5, 6):
                return {}
            if release_type not in (1, 2, 3):
                continue
            released = _date(row.get("release_date"), timestamp=True)
            if released is None:
                # A malformed eligible row prevents proving a global minimum.
                return {}
            if release_type not in first or released < first[release_type]:
                first[release_type] = released
    return first


def from_details(details: dict, expected_id: int) -> Optional[MovieYears]:
    """Bind accepted years to a valid primary date and the exact TMDb ID."""
    if type(expected_id) is not int or expected_id <= 0 or type(details) is not dict:
        return None
    if type(details.get("id")) is not int or details["id"] != expected_id or _has_error(details):
        return None
    primary = _date(details.get("release_date"))
    if primary is None:
        return None
    years = {primary.year}
    for released in _first_release_dates(details.get("release_dates")).values():
        if released <= primary:
            years.add(released.year)
    return MovieYears(expected_id, primary.year, tuple(sorted(years)))


def accepted_years(evidence, expected_id, fallback_year) -> Tuple[int, ...]:
    """Use same-ID process evidence, otherwise only a valid fallback year."""
    if (
        type(evidence) is MovieYears
        and type(expected_id) is int
        and expected_id > 0
        and type(evidence.tmdb_id) is int
        and evidence.tmdb_id == expected_id
        and type(evidence.primary_year) is int
        and _year(evidence.primary_year) is not None
        and type(evidence.years) is tuple
        and 1 <= len(evidence.years) <= 4
        and all(type(year) is int and _year(year) is not None for year in evidence.years)
        and evidence.years == tuple(sorted(set(evidence.years)))
        and evidence.primary_year in evidence.years
        and all(year <= evidence.primary_year for year in evidence.years)
        and evidence.provenance == PROVENANCE
    ):
        return evidence.years
    fallback = _year(fallback_year)
    return (fallback,) if fallback is not None else ()
