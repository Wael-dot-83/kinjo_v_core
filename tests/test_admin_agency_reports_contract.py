from agency_reports_service import AgencyReportsService


class DummyQuery:
    def __init__(self, scalar_value=0):
        self.scalar_value = scalar_value
    def scalar(self):
        return self.scalar_value


class DummyDB:
    def query(self, *args, **kwargs):
        return DummyQuery(0)


def test_catalog_summary_contract_without_database_rows():
    service = AgencyReportsService(DummyDB())
    summary = service.summary()
    assert summary["agency_count"] == 7
    assert summary["privacy_level"] == "aggregated_only"
    assert summary["report_count"] >= summary["ready_report_count"]
