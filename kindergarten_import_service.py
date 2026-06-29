"""
Excel Import Service for Kindergartens
Handles reading Excel files, validating data, and importing into database.
"""
import os
import re
import uuid
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from fastapi import HTTPException

from models import ImportedKindergarten, ImportLog
from database import get_db

logger = logging.getLogger(__name__)


class KindergartenImportService:
    """Service for importing kindergartens from Excel files."""

    # Header mapping from Arabic to internal fields
    HEADER_MAPPING = {
        "اسم الروضة (عربي)": "name_ar",
        "اسم الروضة (إنجليزي)": "name_en",
        "المحافظة": "governorate",
        "المدينة": "city",
        "المنطقة": "area",
        "العنوان التفصيلي": "detailed_address",
        "رقم الهاتف": "phone"
    }

    REQUIRED_FIELDS = ["name_ar", "governorate", "city", "phone"]

    def __init__(self, db: Session):
        self.db = db

    def normalize_phone(self, phone: str) -> str:
        """Normalize phone number: remove spaces/dashes, keep leading 0."""
        if not phone:
            return ""
        # Remove spaces, dashes, parentheses
        phone = re.sub(r'[\s\-\(\)]', '', str(phone))
        # Keep leading 0
        if phone.startswith('0'):
            return phone
        # If starts with +962, keep as is
        if phone.startswith('+962'):
            return phone
        # Otherwise, assume Jordan and add 0 if not present
        if not phone.startswith('0'):
            phone = '0' + phone
        return phone

    def validate_row(self, row: Dict[str, Any], row_num: int) -> Dict[str, Any]:
        """Validate a single row and return cleaned data or errors."""
        errors = []
        cleaned = {}

        for arabic_header, field in self.HEADER_MAPPING.items():
            value = row.get(arabic_header, "")
            # Handle different data types from pandas
            if pd.isna(value):
                value = ""
            else:
                value = str(value).strip()

            if field in self.REQUIRED_FIELDS and not value:
                errors.append(f"Missing required field: {arabic_header}")
                continue

            if field == "phone":
                value = self.normalize_phone(value)
                if not value:
                    errors.append(f"Invalid phone number: {arabic_header}")
                    continue
                # Basic phone validation for Jordan (10 digits starting with 06, 07, 08, 09)
                if not re.match(r'^0[6789]\d{8}$', value):
                    errors.append(f"Invalid Jordan phone format: {value}")
                    continue

            cleaned[field] = value

        if errors:
            return {"errors": errors, "row_num": row_num}

        return cleaned

    def import_from_excel(self, file_path: str, file_name: str = None) -> Dict[str, Any]:
        """Import kindergartens from Excel file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            # Read Excel file
            df = pd.read_excel(file_path, sheet_name=0, header=0)
        except (OSError, ValueError, ImportError) as e:
            raise ValueError(f"Error reading Excel file: {str(e)}")

        total_rows = len(df)
        imported_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        # Process in batches
        batch_size = 200
        for i in range(0, total_rows, batch_size):
            batch_df = df.iloc[i:i+batch_size]
            batch_results = self._process_batch(batch_df, i+1)
            imported_count += batch_results["imported"]
            updated_count += batch_results["updated"]
            skipped_count += batch_results["skipped"]
            errors.extend(batch_results["errors"])

        # Create import log
        import_log = ImportLog(
            file_name=file_name or os.path.basename(file_path),
            stored_file_path=file_path,
            total_rows=total_rows,
            imported_count=imported_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            errors_json=errors if errors else None
        )
        self.db.add(import_log)
        self.db.commit()

        return {
            "total_rows": total_rows,
            "imported_count": imported_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "errors": errors,
            "import_log_id": import_log.id
        }

    def _process_batch(self, df: pd.DataFrame, start_row: int) -> Dict[str, Any]:
        """Process a batch of rows."""
        imported = 0
        updated = 0
        skipped = 0
        errors = []

        for idx, row in df.iterrows():
            row_num = start_row + idx
            validated = self.validate_row(row.to_dict(), row_num)

            if "errors" in validated:
                errors.append({
                    "row": row_num,
                    "errors": validated["errors"]
                })
                skipped += 1
                continue

            # Try to upsert
            try:
                result = self._upsert_kindergarten(validated)
                if result["created"]:
                    imported += 1
                else:
                    updated += 1
            except (IntegrityError, SQLAlchemyError, KeyError, TypeError, ValueError) as e:
                self.db.rollback()
                logger.warning("Failed to import kindergarten row %s: %s", row_num, str(e), exc_info=isinstance(e, (IntegrityError, SQLAlchemyError)))
                errors.append({
                    "row": row_num,
                    "errors": [f"Database error: {str(e)}"]
                })
                skipped += 1

        return {
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
            "errors": errors
        }

    def _upsert_kindergarten(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert a kindergarten record."""
        # Check if exists
        existing = self.db.query(ImportedKindergarten).filter(
            and_(
                ImportedKindergarten.name_ar == data["name_ar"],
                ImportedKindergarten.district == data["city"],
                ImportedKindergarten.phone == data["phone"]
            )
        ).first()

        if existing:
            # Update
            for key, value in data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = pd.Timestamp.now()
            created = False
        else:
            # Create
            kg = ImportedKindergarten(**data)
            self.db.add(kg)
            created = True

        self.db.commit()
        return {"created": created}

    def get_imported_kindergartens(self, page: int = 1, per_page: int = 50,
                                   governorate: str = None, district: str = None,
                                   search: str = None) -> Dict[str, Any]:
        """Get paginated list of imported kindergartens."""
        query = self.db.query(ImportedKindergarten)

        if governorate:
            query = query.filter(ImportedKindergarten.governorate == governorate)
        if district:
            query = query.filter(ImportedKindergarten.district == district)
        if search:
            search_filter = f"%{search}%"
            query = query.filter(
                or_(
                    ImportedKindergarten.name_ar.ilike(search_filter),
                    ImportedKindergarten.name_en.ilike(search_filter),
                    ImportedKindergarten.phone.ilike(search_filter)
                )
            )

        total = query.count()
        kindergartens = query.offset((page - 1) * per_page).limit(per_page).all()

        return {
            "kindergartens": kindergartens,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page
        }

    def get_import_logs(self, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """Get paginated import logs."""
        query = self.db.query(ImportLog).order_by(ImportLog.created_at.desc())
        total = query.count()
        logs = query.offset((page - 1) * per_page).limit(per_page).all()

        return {
            "logs": logs,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page
        }


def import_kindergartens_cli(file_path: str) -> None:
    """CLI function to import kindergartens."""
    db = next(get_db())
    try:
        service = KindergartenImportService(db)
        result = service.import_from_excel(file_path)

        print("Import Summary:")
        print(f"Total rows: {result['total_rows']}")
        print(f"Imported: {result['imported_count']}")
        print(f"Updated: {result['updated_count']}")
        print(f"Skipped: {result['skipped_count']}")
        if result['errors']:
            print(f"Errors: {len(result['errors'])}")
            for error in result['errors'][:5]:  # Show first 5
                print(f"  Row {error['row']}: {error['errors']}")
            if len(result['errors']) > 5:
                print(f"  ... and {len(result['errors']) - 5} more")

    except (FileNotFoundError, ValueError, IntegrityError, SQLAlchemyError, OSError) as e:
        logger.error("Kindergarten import failed for file %s: %s", file_path, str(e), exc_info=True)
        print(f"Import failed: {str(e)}")
        raise
    finally:
        db.close()