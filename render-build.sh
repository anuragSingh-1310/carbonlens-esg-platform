#!/usr/bin/env bash
# exit on error
set -o errexit

# Install Tesseract OCR system dependency
apt-get update && apt-get install -y tesseract-ocr

# Install Python dependencies
pip install -r requirements.txt

# Run database migrations and collect static files
python manage.py migrate
python manage.py collectstatic --no-input
