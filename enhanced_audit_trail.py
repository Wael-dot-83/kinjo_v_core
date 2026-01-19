"""
Enhanced audit trail for KPI calculations in KinJo
"""
from typing import Dict, Any
import logging

class EnhancedAuditTrail:
    @staticmethod
    def log_kpi_calc(event: str, details: Dict[str, Any]):
        logging.info(f"KPI_CALC: {event} | {details}")

    @staticmethod
    def log_anomaly(event: str, details: Dict[str, Any]):
        logging.warning(f"KPI_ANOMALY: {event} | {details}")

    @staticmethod
    def log_data_quality(event: str, details: Dict[str, Any]):
        logging.info(f"KPI_DATA_QUALITY: {event} | {details}")
