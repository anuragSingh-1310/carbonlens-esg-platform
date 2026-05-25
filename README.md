# CarbonLens

CarbonLens is a full stack ESG ingestion and audit platform built using React and Django REST Framework.

The system allows companies to upload sustainability-related data files such as fuel procurement, electricity usage, and travel records. The platform processes the uploaded data, normalizes emissions data into Scope 1, Scope 2, and Scope 3 categories, detects anomalies automatically, and provides an audit dashboard for sustainability analysts.

---

# Features

## ESG File Upload System
Users can upload:
- SAP Procurement CSV files
- Utility Electricity CSV files
- Corporate Travel JSON files

---

## Smart AI/OCR Document Ingestion [New]
Users can upload utility bills, fuel invoices, travel receipts, logistics bills, and invoice images (PDF, PNG, JPG, JPEG). The system:
- Performs OCR text extraction and image cleaning automatically.
- Classifies bills into Scope 1, Scope 2, and Scope 3 emission scopes.
- Parses key data like quantity, unit, invoice date, supplier name, facility, and amount.
- Displays a live "Smart Verification" preview card to review, edit, and approve data before committing.
- Automatically flags duplicates and readability warnings.

---

## Automatic ESG Classification
The backend automatically:
- Classifies emissions into Scope 1, Scope 2, and Scope 3
- Converts units into normalized formats
- Stores raw uploaded records for auditing

---

## Anomaly Detection
The platform automatically detects:
- Extremely large quantities
- Suspicious values
- Abnormal usage spikes

Flagged records are highlighted in the dashboard.

---

## Audit Workflow
Auditors can:
- Review uploaded records
- Approve records
- Flag anomalies
- Edit incorrect data
- Perform bulk approvals

---

## Dashboard Analytics
The dashboard provides:
- Total ingested records
- Pending audits
- Flagged anomalies
- Approved records
- Scope distribution metrics

---

# Tech Stack

## Frontend
- React
- Axios
- Lucide React

## Backend
- Django
- Django REST Framework
- pdfplumber (for PDF text vectors)
- pytesseract & Pillow (for image character recognition & preprocessors)

## Database
- SQLite

## Deployment
- Render (Backend)
- Vercel / Netlify (Frontend)

---

# Project Structure

```text
CarbonLens/
│
├── backend/
│   └── settings.py
├── carbon_app/
│   ├── services/       # Modular Ingestion package
│   ├── models.py
│   ├── views.py
│   └── urls.py
├── frontend/
│   └── src/Dashboard.jsx
├── manage.py
├── requirements.txt
├── Procfile
└── README.md
```

---

# Setup & Run Instructions

## 1. Quick Installation
Install all Python dependencies in the root project directory:
```powershell
pip install -r requirements.txt
```

## 2. Tesseract OCR System Setup
Since the Smart Upload reads image text, you must have Tesseract OCR on your machine:
- **Windows**: Installs automatically! Our backend auto-detects Tesseract at `C:\Program Files\Tesseract-OCR\tesseract.exe`.
- **Linux (Ubuntu)**: `sudo apt-get install tesseract-ocr`
- **macOS**: `brew install tesseract`

## 3. Run Backend Server
```powershell
python manage.py runserver
```

## 4. Run Frontend App
In a new terminal, navigate to the `frontend/` folder and run:
```powershell
npm run start
```