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
├── carbon_app/
├── frontend/
├── sample_data/
├── manage.py
├── requirements.txt
├── Procfile
└── README.md