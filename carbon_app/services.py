import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import (
    RawIngestionJob,
    RawDataRow,
    EmissionActivityRecord,
    AuditLog
)

# Shared Airport Route Constants (in km)
AIRPORT_DISTANCES = {
    ("BOM", "DEL"): Decimal("1140.0"),
    ("DEL", "LHR"): Decimal("6710.0"),
    ("BLR", "SIN"): Decimal("3160.0"),
}


def parse_date_flexible(date_str):
    """
    Parses common enterprise date formats into standard Python date objects.
    Supports YYYYMMDD, DD.MM.YYYY, YYYY-MM-DD, DD/MM/YYYY.
    """
    if not date_str:
        raise ValueError("Date field is empty or missing")
    
    date_str = str(date_str).strip()
    
    formats = [
        "%Y%m%d",       # SAP standard: e.g. 20260524
        "%d.%m.%Y",     # SAP alternate: e.g. 24.05.2026
        "%Y-%m-%d",     # ISO date standard: e.g. 2026-05-24
        "%d/%m/%Y",     # Slash format: e.g. 24/05/2026
        "%m/%d/%Y",     # US slash format: e.g. 05/24/2026
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
            
    raise ValueError(f"Could not parse date string '{date_str}' with any supported formats.")


def parse_decimal_safe(value, field_name):
    """
    Safely parses numeric fields into high-precision Decimal values.
    """
    if value is None or str(value).strip() == "":
        raise ValueError(f"Field '{field_name}' is missing or empty")
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid decimal value for field '{field_name}': '{value}'")


def get_airport_distance(origin, destination):
    """
    Resolves distance (in km) between airport pairs (bidirectional lookup).
    If unknown, falls back to a standard estimate and reports that estimation occurred.
    """
    origin = str(origin).upper().strip()
    destination = str(destination).upper().strip()
    
    if not origin or not destination:
        raise ValueError("Origin and Destination airport codes are required")
        
    # Sort codes to support bidirectional matching (e.g. BOM-DEL and DEL-BOM)
    key = tuple(sorted([origin, destination]))
    
    distance = AIRPORT_DISTANCES.get(key)
    if distance is not None:
        return distance, False  # Exact match, not an estimated fallback
        
    # Default fallback estimate for unknown airport connections
    return Decimal("1500.0"), True  # Estimated fallback


# ==========================================
# 1. SAP Procurement/Fuel CSV Ingestion
# ==========================================

def classify_sap_material(material_name):
    """
    Maps SAP material descriptions to carbon accounting scopes and categories.
    """
    material_lower = str(material_name).lower().strip()
    
    # Heavy fuel oil, fuels, or diesel map to Scope 1 (Direct Emissions)
    if any(keyword in material_lower for keyword in ["heavy fuel oil", "fuel oil", "diesel", "fuel"]):
        return (
            EmissionActivityRecord.ScopeType.SCOPE_1,
            "STATIONARY_FUEL",
            "LITERS"
        )
    # General procurement goods or office supply map to Scope 3 (Purchased Goods and Services)
    elif any(keyword in material_lower for keyword in ["procurement goods", "goods", "office", "supply"]):
        return (
            EmissionActivityRecord.ScopeType.SCOPE_3,
            "PURCHASED_GOODS",
            "UNITS"
        )
    else:
        # Fallback corporate procurement classification
        return (
            EmissionActivityRecord.ScopeType.SCOPE_3,
            "OTHER_PROCUREMENT",
            "UNITS"
        )


def normalize_sap_quantity(quantity, unit):
    """
    Converts source units to standard sustainability metric targets.
    """
    unit_upper = str(unit).upper().strip()
    
    if unit_upper in ["GAL", "GALLONS", "GALLON"]:
        return quantity * Decimal("3.78541"), "LITERS"
    elif unit_upper in ["L", "LTR", "LITERS", "LITER"]:
        return quantity, "LITERS"
    else:
        return quantity, unit_upper  # Maintain original unit structure if not convertible


def ingest_sap_procurement_csv(organization, job, csv_file_content):
    """
    Ingests and normalizes SAP CSV exports.
    Expected headers: MATNR, MENG, MEINS, WERKS, BUDAT
    """
    # 1. Check CSV headers structure
    try:
        csv_file = io.StringIO(csv_file_content)
        reader = csv.DictReader(csv_file)
        
        if not reader.fieldnames:
            raise ValueError("CSV file is empty or lacks readable columns")
            
        required_headers = {"MATNR", "MENG", "MEINS", "WERKS", "BUDAT"}
        missing_headers = required_headers - set(reader.fieldnames)
        if missing_headers:
            raise ValueError(f"Missing required CSV columns: {', '.join(missing_headers)}")
            
        rows_data = list(reader)
    except Exception as e:
        job.status = RawIngestionJob.JobStatus.FAILED
        job.error_summary = f"File reading/structure error: {str(e)}"
        job.save()
        return

    job.status = RawIngestionJob.JobStatus.PROCESSING
    job.save()

    # 2. Phase 1: Store all imported rows into RawDataRow (Atomic bulk-like pattern)
    raw_data_rows = []
    for idx, row in enumerate(rows_data, start=1):
        raw_row = RawDataRow.objects.create(
            organization=organization,
            job=job,
            payload=row,
            row_index=idx,
            status=RawDataRow.RowStatus.UNPROCESSED
        )
        raw_data_rows.append(raw_row)

    # 3. Phase 2: Sequential transactional normalization
    for raw_row in raw_data_rows:
        try:
            with transaction.atomic():
                payload = raw_row.payload
                
                # Parse inputs safely
                original_qty = parse_decimal_safe(payload["MENG"], "MENG")
                original_unit = payload["MEINS"]
                plant_code = payload["WERKS"]
                transaction_date = parse_date_flexible(payload["BUDAT"])
                
                # Perform business scoping and conversions
                scope, category, target_unit = classify_sap_material(payload["MATNR"])
                norm_qty, norm_unit = normalize_sap_quantity(original_qty, original_unit)
                
                # Build activity record (anomaly heuristics automatically run inside model save)
                activity = EmissionActivityRecord(
                    organization=organization,
                    raw_row=raw_row,
                    scope=scope,
                    category=category,
                    original_quantity=original_qty,
                    original_unit=original_unit,
                    normalized_quantity=norm_qty,
                    normalized_unit=norm_unit,
                    transaction_date=transaction_date,
                    plant_facility_code=plant_code
                )
                activity.save()  # Triggers save() lifecycle which logs to audit trail and checks anomalies
                
                # Mark as successful
                raw_row.status = RawDataRow.RowStatus.PROCESSED
                raw_row.save()
                
        except Exception as e:
            # Row processing failed; rollback atomic savepoint and log the trace locally
            raw_row.status = RawDataRow.RowStatus.ERROR
            raw_row.error_message = str(e)
            raw_row.save()

    # 4. Finalize Ingestion Job status
    has_errors = RawDataRow.objects.filter(job=job, status=RawDataRow.RowStatus.ERROR).exists()
    job.status = RawIngestionJob.JobStatus.COMPLETED
    if has_errors:
        job.error_summary = "Completed with some row parsing errors. Check RawDataRow logs."
    job.save()


# ==========================================
# 2. Utility Electricity CSV Ingestion
# ==========================================

def ingest_utility_electricity_csv(organization, job, csv_file_content):
    """
    Ingests and normalizes Utility Electricity CSV exports.
    Expected headers: Account_Number, Start_Date, End_Date, Usage_kWh, Meter_Multiplier
    """
    try:
        csv_file = io.StringIO(csv_file_content)
        reader = csv.DictReader(csv_file)
        
        if not reader.fieldnames:
            raise ValueError("CSV file is empty or lacks readable columns")
            
        required_headers = {"Account_Number", "Start_Date", "End_Date", "Usage_kWh", "Meter_Multiplier"}
        missing_headers = required_headers - set(reader.fieldnames)
        if missing_headers:
            raise ValueError(f"Missing required CSV columns: {', '.join(missing_headers)}")
            
        rows_data = list(reader)
    except Exception as e:
        job.status = RawIngestionJob.JobStatus.FAILED
        job.error_summary = f"File reading/structure error: {str(e)}"
        job.save()
        return

    job.status = RawIngestionJob.JobStatus.PROCESSING
    job.save()

    # Phase 1: Store Raw Lines
    raw_data_rows = []
    for idx, row in enumerate(rows_data, start=1):
        raw_row = RawDataRow.objects.create(
            organization=organization,
            job=job,
            payload=row,
            row_index=idx,
            status=RawDataRow.RowStatus.UNPROCESSED
        )
        raw_data_rows.append(raw_row)

    # Phase 2: Normalize
    for raw_row in raw_data_rows:
        try:
            with transaction.atomic():
                payload = raw_row.payload
                
                # Parse
                usage_val = parse_decimal_safe(payload["Usage_kWh"], "Usage_kWh")
                multiplier = parse_decimal_safe(payload["Meter_Multiplier"], "Meter_Multiplier")
                
                # Calculate normalized quantity
                norm_qty = usage_val * multiplier
                norm_unit = "kWh"
                
                # Extract and format dates
                # Maps End_Date as active transaction date context
                transaction_date = parse_date_flexible(payload["End_Date"])
                start_date_parsed = parse_date_flexible(payload["Start_Date"])
                
                # Save normalized database records (Scope 2 Purchased Electricity)
                activity = EmissionActivityRecord(
                    organization=organization,
                    raw_row=raw_row,
                    scope=EmissionActivityRecord.ScopeType.SCOPE_2,
                    category="PURCHASED_ELECTRICITY",
                    original_quantity=usage_val,
                    original_unit="kWh",
                    normalized_quantity=norm_qty,
                    normalized_unit=norm_unit,
                    transaction_date=transaction_date,
                    plant_facility_code=payload["Account_Number"] # Map utility account number to local facility code context
                )
                
                # Extra Business anomaly flagging logic directly from service tier
                # Flag extreme meter configurations or spikes manually if multiplier or quantity exceeds parameters
                service_flags = []
                if multiplier > Decimal("100.0"):
                    service_flags.append(f"Suspiciously high meter multiplier ({multiplier})")
                if norm_qty > Decimal("100000.0"):
                    service_flags.append(f"Electricity consumption spike detected ({norm_qty} kWh)")
                
                if service_flags:
                    activity.review_status = EmissionActivityRecord.ReviewStatus.FLAGGED
                    activity.anomaly_flag_reason = " | ".join(service_flags)
                
                activity.save()
                
                raw_row.status = RawDataRow.RowStatus.PROCESSED
                raw_row.save()
                
        except Exception as e:
            raw_row.status = RawDataRow.RowStatus.ERROR
            raw_row.error_message = str(e)
            raw_row.save()

    # Finalize
    has_errors = RawDataRow.objects.filter(job=job, status=RawDataRow.RowStatus.ERROR).exists()
    job.status = RawIngestionJob.JobStatus.COMPLETED
    if has_errors:
        job.error_summary = "Completed with some row parsing errors. Check RawDataRow logs."
    job.save()


# ==========================================
# 3. Corporate Travel JSON Ingestion
# ==========================================

def ingest_corporate_travel_json(organization, job, json_payload):
    """
    Ingests and normalizes Corporate Travel API JSON datasets.
    Expected elements contain booking_id, employee_email, origin_airport, destination_airport, cabin_class
    """
    try:
        if isinstance(json_payload, str):
            rows_data = json.loads(json_payload)
        else:
            rows_data = json_payload  # Already a python list

        if not isinstance(rows_data, list):
            raise ValueError("JSON root structure must be a list of records")
            
        required_keys = {"booking_id", "employee_email", "origin_airport", "destination_airport", "cabin_class"}
        
        # Quick validation of root items
        if len(rows_data) > 0:
            first_item = rows_data[0]
            missing_keys = required_keys - set(first_item.keys())
            if missing_keys:
                raise ValueError(f"Missing required JSON attributes: {', '.join(missing_keys)}")
                
    except Exception as e:
        job.status = RawIngestionJob.JobStatus.FAILED
        job.error_summary = f"JSON payload syntax/keys error: {str(e)}"
        job.save()
        return

    job.status = RawIngestionJob.JobStatus.PROCESSING
    job.save()

    # Phase 1: Store Raw Lines
    raw_data_rows = []
    for idx, row in enumerate(rows_data, start=1):
        raw_row = RawDataRow.objects.create(
            organization=organization,
            job=job,
            payload=row,
            row_index=idx,
            status=RawDataRow.RowStatus.UNPROCESSED
        )
        raw_data_rows.append(raw_row)

    # Phase 2: Normalize
    for raw_row in raw_data_rows:
        try:
            with transaction.atomic():
                payload = raw_row.payload
                
                origin = payload["origin_airport"]
                destination = payload["destination_airport"]
                
                # Estimate distance from pair maps
                distance_km, is_estimate = get_airport_distance(origin, destination)
                
                # Cabin class emission factors adjustment helper (e.g. business/first class weighs heavier)
                cabin_factor = Decimal("1.0")
                cabin_upper = str(payload["cabin_class"]).upper().strip()
                if "BUSINESS" in cabin_upper:
                    cabin_factor = Decimal("1.5")
                elif "FIRST" in cabin_upper:
                    cabin_factor = Decimal("2.0")
                
                # Standard business travel emission estimation: km * cabin weight multiplier
                norm_qty = distance_km * cabin_factor
                norm_unit = "km-CO2e-factor"
                
                # Map to Scope 3 Business Travel
                # Set transaction_date as active system time if missing from the booking feed
                tx_date_raw = payload.get("booking_date") or payload.get("travel_date")
                if tx_date_raw:
                    transaction_date = parse_date_flexible(tx_date_raw)
                else:
                    transaction_date = datetime.now().date()
                
                activity = EmissionActivityRecord(
                    organization=organization,
                    raw_row=raw_row,
                    scope=EmissionActivityRecord.ScopeType.SCOPE_3,
                    category="BUSINESS_TRAVEL",
                    original_quantity=distance_km,
                    original_unit="km",
                    normalized_quantity=norm_qty,
                    normalized_unit=norm_unit,
                    transaction_date=transaction_date,
                    plant_facility_code="HQ_TRAVEL"  # Corporate HQ designated travel booking pool
                )
                
                # Flag anomalies/estimates for auditor checklist visibility
                service_flags = []
                if is_estimate:
                    service_flags.append(f"Airport distance estimated due to unknown route pair ({origin}-{destination})")
                if norm_qty > Decimal("10000.0"):
                    service_flags.append(f"Extreme corporate travel single booking flight distance detected ({norm_qty})")
                
                if service_flags:
                    activity.review_status = EmissionActivityRecord.ReviewStatus.FLAGGED
                    activity.anomaly_flag_reason = " | ".join(service_flags)
                    
                activity.save()
                
                raw_row.status = RawDataRow.RowStatus.PROCESSED
                raw_row.save()
                
        except Exception as e:
            raw_row.status = RawDataRow.RowStatus.ERROR
            raw_row.error_message = str(e)
            raw_row.save()

    # Finalize Ingestion Job
    has_errors = RawDataRow.objects.filter(job=job, status=RawDataRow.RowStatus.ERROR).exists()
    job.status = RawIngestionJob.JobStatus.COMPLETED
    if has_errors:
        job.error_summary = "Completed with some row parsing errors. Check RawDataRow logs."
    job.save()
