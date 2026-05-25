# Re-export legacy functions to preserve existing CSV & JSON pipelines
from .legacy import (
    parse_date_flexible,
    parse_decimal_safe,
    get_airport_distance,
    classify_sap_material,
    normalize_sap_quantity,
    ingest_sap_procurement_csv,
    ingest_utility_electricity_csv,
    ingest_corporate_travel_json
)

# Export new AI/OCR document ingestion pipeline
from .ocr_service import extract_document_text
from .document_classifier import classify_document
from .parser_service import extract_entities
from .validation_service import (
    validate_uploaded_file,
    check_for_duplicates,
    assess_ocr_readability
)
from .emission_mapper import create_esg_records, normalize_quantity_by_unit
