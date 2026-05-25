import re
import logging
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)

# Sample regular expression patterns for high-precision entity extraction
PATTERNS = {
    "quantity": [
        r"(?:usage|consumption|quantity|qty|metered|billed|meng)\s*(?:amount|value|qty)?\s*[:\-\s]+([\d,]+(?:\.\d+)?)",
        r"([\d,]+(?:\.\d+)?)\s*(?:kwh|liters|litres|l|gal|gallons|km|miles|units|pcs)\b",
        r"(?:total\s+)?quantity\s*[:\-\s]+([\d,]+(?:\.\d+)?)",
        r"\b(?:qty|quantity)\b\s*[:\-\s]+([\d,]+(?:\.\d+)?)"
    ],
    "unit": [
        r"\b(kwh|liters|litres|l|gal|gallons|km|miles|units|pcs|mtrs|mtr|meters)\b",
        r"(?:unit|meins)\s*[:\-\s]+([a-zA-Z]{1,8})\b"
    ],
    "amount": [
        r"(?:total|amount|due|charge|cost|sum|total\s+amount|invoice\s+amount)\s*(?:due|charge)?\s*(?:\$|€|£|₹|rs\.?|usd)?\s*[:\-\s]+([\d,]+\.\d{2})\b",
        r"(?:\$|€|£|₹|rs\.?)\s*([\d,]+\.\d{2})\b",
        r"\bamount\b\s*[:\-\s]+(?:\$|€|£|₹|rs\.?|usd)?\s*([\d,]+\.\d{2})\b"
    ],
    "date": [
        r"\b\d{4}-\d{2}-\d{2}\b",                                    # 2026-05-25
        r"\b\d{2}/\d{2}/\d{4}\b",                                    # 25/05/2026 or 05/25/2026
        r"\b\d{2}\.\d{2}\.\d{4}\b",                                    # 25.05.2026
        r"\b\d{8}\b",                                                 # 20260525 (SAP format)
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b", # May 25, 2026
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b"  # 25 May 2026
    ],
    "vendor": [
        r"(?:vendor|supplier|issuer|merchant|seller|billed\s+by)\s*[:\-\s]+([a-zA-Z0-9 \t,\.\-&]{2,40})",
        r"(?:from|invoice\s+by)\s*[:\-\s]+([a-zA-Z0-9 \t,\.\-&]{2,40})",
        r"\b(?:Acme|Shell|Chevron|DHL|FedEx|BP|Exxon|Tata Power|PG&E|Uber|Lyft|Air India|British Airways|Delta|Lufthansa|Electric Co)\b"
    ],
    "facility": [
        r"(?:account|meter|facility|plant|werks|location|branch|site)\s*(?:number|no|code|id)?\s*[:\-]+\s*([a-zA-Z0-9\-_]{3,20})",
        r"\b(?:PLANT_[A-Z]|WERKS_\d{4}|HQ_[A-Z]+|ACCT-\d{4,10})\b"
    ]
}


def parse_date_safely(date_str):
    """
    Tries to parse extracted date string. Falls back to flexible date formats.
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Try common explicit string patterns
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d.%m.%Y",
        "%Y%m%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
            
    # Clean string if separators vary
    clean_date = re.sub(r'[\/\.]', '-', date_str)
    try:
        return datetime.strptime(clean_date, "%Y-%m-%d").date()
    except ValueError:
        pass
        
    return None


def clean_regex_match(match_str):
    """
    Cleans leading/trailing spaces and punctuations from regex matches.
    """
    if not match_str:
        return ""
    return match_str.strip().strip(",-: \t\n")


def extract_entities(text):
    """
    Applies multi-pattern regular expressions to parse transactional entities from OCR text.
    Returns:
        parsed_data: dict of extracted elements
    """
    text_lines = text.split("\n")
    parsed_data = {
        "quantity": None,
        "unit": None,
        "invoice_date": None,
        "vendor": None,
        "facility": None,
        "invoice_amount": None,
        "activity_type": None
    }
    
    # 1. Extract Invoice Amount (look for matching patterns)
    for pattern in PATTERNS["amount"]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                amt_str = match.group(1).replace(",", "")
                parsed_data["invoice_amount"] = Decimal(amt_str)
                break
            except Exception:
                continue

    # 2. Extract Quantity/Consumption
    for pattern in PATTERNS["quantity"]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                qty_str = match.group(1).replace(",", "")
                parsed_data["quantity"] = Decimal(qty_str)
                break
            except Exception:
                continue

    # 3. Extract Unit
    for pattern in PATTERNS["unit"]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            parsed_data["unit"] = clean_regex_match(match.group(1)).upper()
            break

    # 4. Extract Invoice Date
    for pattern in PATTERNS["date"]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_parsed = parse_date_safely(match.group(0))
            if date_parsed:
                parsed_data["invoice_date"] = date_parsed
                break

    # 5. Extract Vendor
    for pattern in PATTERNS["vendor"]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # If it's a literal match of common names
            matched_val = match.group(0) if len(match.groups()) == 0 else match.group(1)
            parsed_data["vendor"] = clean_regex_match(matched_val)
            break

    # 6. Extract Facility/Account
    for pattern in PATTERNS["facility"]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            matched_val = match.group(0) if len(match.groups()) == 0 else match.group(1)
            parsed_data["facility"] = clean_regex_match(matched_val)
            break

    # 7. Apply smart fallbacks for empty values to guarantee operational resilience
    if parsed_data["unit"] is None:
        text_lower = text.lower()
        if "kwh" in text_lower:
            parsed_data["unit"] = "KWH"
        elif any(w in text_lower for w in ["liter", "liters", "litre", "l"]):
            parsed_data["unit"] = "LITERS"
        elif any(w in text_lower for w in ["gallon", "gallons", "gal"]):
            parsed_data["unit"] = "GALLONS"
        elif any(w in text_lower for w in ["km", "kilometer", "kilometers"]):
            parsed_data["unit"] = "KM"
        elif any(w in text_lower for w in ["mile", "miles"]):
            parsed_data["unit"] = "MILES"
        else:
            parsed_data["unit"] = "UNITS"

    if parsed_data["invoice_date"] is None:
        # Fallback to current date if completely missing
        parsed_data["invoice_date"] = datetime.now().date()

    if parsed_data["vendor"] is None:
        parsed_data["vendor"] = "Unknown ESG Supplier"

    if parsed_data["facility"] is None:
        parsed_data["facility"] = "HQ_FACILITY"

    if parsed_data["quantity"] is None:
        parsed_data["quantity"] = Decimal("0.0")

    if parsed_data["invoice_amount"] is None:
        parsed_data["invoice_amount"] = Decimal("0.0")

    return parsed_data
