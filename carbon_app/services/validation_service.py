import os
import logging
from ..models import EmissionActivityRecord

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg'}

def validate_uploaded_file(file_obj, filename):
    """
    Validates file extensions and catches potential malformed uploads.
    """
    if not file_obj:
        raise ValueError("No file payload was uploaded.")
        
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: '{ext}'. CarbonLens ESG Document Ingestion only accepts PDF, PNG, JPG, and JPEG files."
        )
        
    # Check file size (e.g. limit to 10MB to protect resources)
    if file_obj.size > 10 * 1024 * 1024:
        raise ValueError("File size exceeds the maximum standard limit of 10MB.")


def check_for_duplicates(organization, quantity, unit, transaction_date, facility_code):
    """
    Duplicate detection: Queries existing active records to prevent double-counting of invoices.
    """
    if not quantity or not transaction_date or not facility_code:
        return False, None
        
    # Query matching records within the tenant organization
    existing = EmissionActivityRecord.objects.filter(
        organization=organization,
        original_quantity=quantity,
        original_unit=unit,
        transaction_date=transaction_date,
        plant_facility_code=facility_code
    ).first()
    
    if existing:
        logger.warning(f"Duplicate upload detected: matching record found with ID {existing.id}.")
        return True, existing.id
        
    return False, None


def assess_ocr_readability(text):
    """
    Evaluates OCR output to detect completely scrambled or unreadable text.
    Returns:
        is_readable: bool
        warnings: list of warnings
    """
    warnings = []
    if not text or len(text.strip()) < 15:
        return False, ["Extracted document content is extremely short or blank. OCR processing might have failed due to low contrast or blur."]
        
    # Heuristic: Check density of special/garbage characters as a metric for low confidence
    special_char_count = sum(1 for c in text if not c.isalnum() and not c.isspace())
    char_count = len(text)
    
    special_density = special_char_count / char_count if char_count > 0 else 0
    if special_density > 0.40:
        warnings.append(
            "Extracted text has a high density of non-alphanumeric characters, indicating potential OCR noise or scanner distortion."
        )
        
    # Check if there are common words/numbers
    has_numbers = any(c.isdigit() for c in text)
    if not has_numbers:
        warnings.append("No numeric figures were found in the document text. Quantities and dates could not be parsed.")
        
    return len(warnings) < 2, warnings
