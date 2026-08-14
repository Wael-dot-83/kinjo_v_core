"""Registry resolver: maps agency_code to its service class.

The original ``agency_reports_service.py`` used a giant if/elif chain in
``generate_report`` to dispatch.  This module replaces that with a clean
registry lookup.  Agencies that have not yet been extracted into their own
service class fall back to the legacy ``AgencyReportsService`` monolith.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.agency_reports.base import AbstractAgencyReportService, AgencyReportError

# Registry of agency_code -> service class.
# Each entry is a class implementing AbstractAgencyReportService.
_AGENCY_SERVICES: dict[str, type[AbstractAgencyReportService]] = {}


def register_agency_service(agency_code: str, service_cls: type[AbstractAgencyReportService]) -> None:
    """Register a service class for an agency code."""
    _AGENCY_SERVICES[agency_code] = service_cls


def get_agency_service(agency_code: str, db: Session) -> AbstractAgencyReportService:
    """Resolve and instantiate the service for ``agency_code``.

    Falls back to the legacy ``AgencyReportsService`` monolith for agencies
    that have not yet been extracted into dedicated service classes.
    """
    if agency_code in _AGENCY_SERVICES:
        return _AGENCY_SERVICES[agency_code](db)

    # Fallback: use the legacy monolith for agencies not yet decomposed.
    from agency_reports_service import AgencyReportsService
    return _LegacyAdapter(agency_code, AgencyReportsService(db))


class _LegacyAdapter(AbstractAgencyReportService):
    """Adapter that wraps the legacy ``AgencyReportsService`` monolith so it
    conforms to the new ``AbstractAgencyReportService`` interface.

    This allows a gradual migration: extracted agencies use their own service
    class; unextracted agencies delegate to the monolith without changes to
    the monolith's public API.
    """

    def __init__(self, agency_code: str, legacy: Any):
        self.agency_code = agency_code
        self._legacy = legacy
        # Copy shared attributes from the legacy instance so the base-class
        # helpers (_apply_parent_geo_filters, etc.) work on the same db session.
        super().__init__(legacy.db)

    def list_reports(self) -> list[dict[str, Any]]:
        result = self._legacy.reports_for_agency(self.agency_code)
        return result.get("reports", [])

    def compute_report(
        self, report_code: str, filters: dict[str, Any]
    ) -> dict[str, Any]:
        return self._legacy.generate_report(self.agency_code, report_code, filters)


# Register the NCFA service (extracted).
from services.agency_reports.ncfa_service import NCFAAgencyReportService
register_agency_service("ncfa", NCFAAgencyReportService)
