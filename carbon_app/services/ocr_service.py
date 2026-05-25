import os
import logging
from PIL import Image, ImageOps, ImageEnhance

logger = logging.getLogger(__name__)

# Check if pytesseract is available
try:
    import pytesseract
except ImportError:
    pytesseract = None

# Check if pdfplumber is available
try:
    import pdfplumber
except ImportError:
    pdfplumber = None


def configure_tesseract_path():
    """
    Checks common Tesseract OCR installation locations on Windows and programmatically
    binds the executable path to pytesseract to bypass PATH environment variable issues.
    """
    if pytesseract is None:
        return
        
    try:
        # Standard Windows installation paths
        common_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
            os.path.expandvars(r"%ProgramFiles%\Tesseract-OCR\tesseract.exe"),
        ]

        for path in common_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                logger.info(f"Auto-configured Tesseract binary path: {path}")
                return
    except Exception as e:
        logger.warning(f"Failed to auto-configure Tesseract path: {str(e)}")


def preprocess_image(image_file):
    """
    Applies image preprocessing to improve OCR accuracy.
    Converts to grayscale, enhances contrast, sharpens, and applies thresholding.
    """
    try:
        # Load image with Pillow
        img = Image.open(image_file)
        
        # 1. Grayscale conversion
        img = ImageOps.grayscale(img)
        
        # 2. Resize to enhance resolution if small
        if img.width < 1000 or img.height < 1000:
            img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
            
        # 3. Enhance Contrast
        contrast = ImageEnhance.Contrast(img)
        img = contrast.enhance(2.0)
        
        # 4. Enhance Sharpness
        sharpness = ImageEnhance.Sharpness(img)
        img = sharpness.enhance(1.5)
        
        # 5. Simple thresholding to binary black/white
        img = img.point(lambda x: 0 if x < 128 else 255, '1')
        
        return img
    except Exception as e:
        logger.error(f"Image preprocessing failed: {str(e)}")
        # Fallback to returning original image loaded safely
        try:
            image_file.seek(0)
        except Exception:
            pass
        return Image.open(image_file)


def extract_text_from_pdf(pdf_file):
    """
    Extracts text from PDF files using pdfplumber.
    """
    if pdfplumber is None:
        raise ImportError("pdfplumber package is not installed in the python environment.")
        
    extracted_text = []
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text()
                if page_text:
                    extracted_text.append(page_text)
                else:
                    logger.warning(f"No direct text extractable from PDF page {page_num}.")
    except Exception as e:
        logger.error(f"PDF extraction failed: {str(e)}")
        raise ValueError(f"Failed to read or parse PDF: {str(e)}")
        
    full_text = "\n\n".join(extracted_text).strip()
    if not full_text:
        raise ValueError("PDF file is empty or contains no readable text. If it is a scanned document, please convert it to an image first.")
    return full_text


def extract_text_from_image(image_file):
    """
    Extracts text from an image (PNG, JPG, JPEG) using pytesseract with preprocessing.
    """
    if pytesseract is None:
        raise ImportError("pytesseract package is not installed in the python environment.")
        
    # Auto-configure path in case Tesseract is installed but not added to system PATH
    configure_tesseract_path()
        
    try:
        # Preprocess the image to clean noise and enhance readability
        clean_img = preprocess_image(image_file)
        
        # Run Tesseract OCR
        text = pytesseract.image_to_string(clean_img)
        return text.strip()
    except Exception as e:
        error_msg = str(e)
        if "tesseract is not installed or it's not in your path" in error_msg.lower() or "no such file or directory" in error_msg.lower():
            logger.error("Tesseract-OCR binary was not found on this system.")
            raise RuntimeError(
                "Tesseract OCR engine is not installed on the system, or not configured in system PATH. "
                "Please follow the Tesseract OCR installation instructions in the CarbonLens setup guide."
            )
        raise ValueError(f"Failed during OCR character recognition: {str(e)}")


def extract_document_text(file_obj, filename):
    """
    Universal text extractor that dispatches to the correct engine based on file extension.
    """
    ext = os.path.splitext(filename)[1].lower()
    
    # Ensure read pointer is at start
    try:
        file_obj.seek(0)
    except Exception:
        pass
        
    if ext == '.pdf':
        return extract_text_from_pdf(file_obj)
    elif ext in ['.png', '.jpg', '.jpeg']:
        return extract_text_from_image(file_obj)
    else:
        raise ValueError(f"Unsupported file type: '{ext}'. Supported formats: PDF, PNG, JPG, JPEG.")
