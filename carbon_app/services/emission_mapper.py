from decimal import Decimal
import logging
from ..models import RawIngestionJob, RawDataRow, EmissionActivityRecord

logger = logging.getLogger(__name__)

def normalize_quantity_by_unit(quantity, unit):
    """
    Standardizes quantity into CarbonLens standard sustainability reporting units:
      - GAL/GALLONS/GALLON -> LITERS (heavy fuel oil, diesel, petrol)
      - MILES/MILE -> KM (travel)
      - L/LTR/LITERS/LITER -> LITERS
      - KWH/KILOWATT-HOUR -> kWh (electricity)
    """
    unit_upper = str(unit).upper().strip()
    
    if unit_upper in ["GAL", "GALLONS", "GALLON"]:
        return quantity * Decimal("3.78541"), "LITERS"
    elif unit_upper in ["MILES", "MILE"]:
        return quantity * Decimal("1.60934"), "KM"
    elif unit_upper in ["L", "LTR", "LITERS", "LITER"]:
        return quantity, "LITERS"
    elif unit_upper in ["KWH", "KILOWATT-HOUR", "KILOWATT-HOURS"]:
        return quantity, "kWh"
    elif unit_upper in ["KM", "KMS", "KILOMETER", "KILOMETERS"]:
        return quantity, "KM"
    else:
        return quantity, unit_upper


def create_esg_records(organization, user, filename, file_size, doc_type, scope, category, parsed_data, raw_text):
    """
    Creates RawIngestionJob, RawDataRow, and the corresponding EmissionActivityRecord in Django.
    """
    # 1. Initialize Ingestion Job
    job = RawIngestionJob.objects.create(
        organization=organization,
        source_type="DOCUMENT_OCR",  # matches choices in models
        status=RawIngestionJob.JobStatus.PENDING,
        uploaded_by=user,
        metadata={
            "filename": filename,
            "filesize_bytes": file_size,
            "document_type": doc_type,
            "scope_detected": scope
        }
    )
    
    # 2. Store original OCR payload inside RawDataRow
    raw_row = RawDataRow.objects.create(
        organization=organization,
        job=job,
        payload={
            "filename": filename,
            "ocr_text": raw_text,
            "extracted_entities": {
                "quantity": str(parsed_data["quantity"]),
                "unit": parsed_data["unit"],
                "invoice_date": str(parsed_data["invoice_date"]),
                "vendor": parsed_data["vendor"],
                "facility": parsed_data["facility"],
                "invoice_amount": str(parsed_data["invoice_amount"])
            }
        },
        row_index=1,
        status=RawDataRow.RowStatus.PROCESSED
    )
    
    # 3. Normalize quantity and units
    norm_qty, norm_unit = normalize_quantity_by_unit(parsed_data["quantity"], parsed_data["unit"])
    
    # 4. Initialize EmissionActivityRecord in PENDING review state
    activity = EmissionActivityRecord(
        organization=organization,
        raw_row=raw_row,
        scope=scope,
        category=category,
        original_quantity=parsed_data["quantity"],
        original_unit=parsed_data["unit"],
        normalized_quantity=norm_qty,
        normalized_unit=norm_unit,
        transaction_date=parsed_data["invoice_date"],
        plant_facility_code=parsed_data["facility"]
    )
    
    # Save automatically triggers anomaly checks and creates an AuditLog entry
    activity.save()
    
    # Complete job successfully
    job.status = RawIngestionJob.JobStatus.COMPLETED
    job.save()
    
    return activity
