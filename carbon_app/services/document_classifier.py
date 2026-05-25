import logging
from ..models import EmissionActivityRecord

logger = logging.getLogger(__name__)

# Keywords mapping for each ESG document category
KEYWORDS_MAP = {
    "electricity_bill": {
        "keywords": ["electricity", "kwh", "power bill", "electric", "meter", "utility", "grid", "energy charge", "usage kwh", "kilowatt-hour"],
        "scope": EmissionActivityRecord.ScopeType.SCOPE_2,
        "category": "PURCHASED_ELECTRICITY"
    },
    "fuel_invoice": {
        "keywords": ["fuel", "diesel", "petrol", "gasoline", "generator", "liter", "liters", "gallon", "gallons", "stationary combustion", "fuel combustion", "hsd", "lpg"],
        "scope": EmissionActivityRecord.ScopeType.SCOPE_1,
        "category": "STATIONARY_FUEL"
    },
    "travel_receipt": {
        "keywords": ["travel", "flight", "taxi", "uber", "boarding pass", "airport", "hotel", "cabin class", "passenger", "km", "miles", "railway", "train", "taxi fare"],
        "scope": EmissionActivityRecord.ScopeType.SCOPE_3,
        "category": "BUSINESS_TRAVEL"
    },
    "shipping_invoice": {
        "keywords": ["shipping", "freight", "logistics", "transport", "carrier", "cargo", "delivery", "shipping cost", "freight charge", "supplier transport"],
        "scope": EmissionActivityRecord.ScopeType.SCOPE_3,
        "category": "SUPPLIER_TRANSPORT"
    },
    "procurement_bill": {
        "keywords": ["procurement", "purchased goods", "materials", "office supply", "vendor", "supplier", "purchase order", "goods", "supply", "qty", "quantity", "unit cost", "procured"],
        "scope": EmissionActivityRecord.ScopeType.SCOPE_3,
        "category": "PURCHASED_GOODS"
    }
}


def classify_document(text):
    """
    Analyzes raw text using token density and keyword frequency checks.
    Returns:
        document_type: str (e.g. 'electricity_bill', 'fuel_invoice', etc.)
        scope: str (e.g. 'SCOPE_1', 'SCOPE_2', 'SCOPE_3')
        category: str (e.g. 'PURCHASED_ELECTRICITY', 'STATIONARY_FUEL', etc.)
        confidence: float (0.0 to 1.0)
    """
    text_lower = text.lower()
    scores = {}
    
    for doc_type, info in KEYWORDS_MAP.items():
        score = 0
        for kw in info["keywords"]:
            count = text_lower.count(kw)
            if count > 0:
                # Add score proportional to keyword frequency
                score += count * 2.0
                
        if score > 0:
            scores[doc_type] = score
            
    if not scores:
        # Fallback default when no keywords are matched
        return "procurement_bill", EmissionActivityRecord.ScopeType.SCOPE_3, "PURCHASED_GOODS", 0.35
        
    # Sort and pick the highest scoring document type
    best_doc_type = max(scores, key=scores.get)
    best_score = scores[best_doc_type]
    
    # Calculate confidence based on score relative to total keywords found
    total_score = sum(scores.values())
    confidence = round(best_score / total_score, 2) if total_score > 0 else 0.50
    
    # Bound confidence values
    confidence = max(0.45, min(confidence, 0.99))
    
    matched_info = KEYWORDS_MAP[best_doc_type]
    return best_doc_type, matched_info["scope"], matched_info["category"], confidence
