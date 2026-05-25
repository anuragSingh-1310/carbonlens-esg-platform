from decimal import Decimal
from datetime import date
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Organization,
    RawIngestionJob,
    RawDataRow,
    EmissionActivityRecord,
    AuditLog
)
from .services import (
    classify_document,
    extract_entities,
    check_for_duplicates,
    assess_ocr_readability,
    normalize_quantity_by_unit
)

User = get_user_model()


class ServiceTierTests(TestCase):
    """
    Tests the modular backend services: classification, regex parsing, normalization, and validation.
    """

    def test_document_classification(self):
        # 1. Test electricity bill keywords matching Scope 2
        text_elec = "Monthly Utility Invoice\nUsage Charge: 4500 kWh\nTata Power Corp Grid"
        doc_type, scope, category, confidence = classify_document(text_elec)
        self.assertEqual(doc_type, "electricity_bill")
        self.assertEqual(scope, EmissionActivityRecord.ScopeType.SCOPE_2)
        self.assertEqual(category, "PURCHASED_ELECTRICITY")
        self.assertGreaterEqual(confidence, 0.5)

        # 2. Test fuel invoice keywords matching Scope 1
        text_fuel = "Diesel Procurement Bill\nAmount Billed: 500 liters of Heavy Fuel Oil for standby Generator"
        doc_type, scope, category, confidence = classify_document(text_fuel)
        self.assertEqual(doc_type, "fuel_invoice")
        self.assertEqual(scope, EmissionActivityRecord.ScopeType.SCOPE_1)
        self.assertEqual(category, "STATIONARY_FUEL")

        # 3. Test travel receipt keywords matching Scope 3
        text_travel = "Corporate Travel Booking\nFlight DEL to BOM\nExecutive Cabin Class: Business"
        doc_type, scope, category, confidence = classify_document(text_travel)
        self.assertEqual(doc_type, "travel_receipt")
        self.assertEqual(scope, EmissionActivityRecord.ScopeType.SCOPE_3)
        self.assertEqual(category, "BUSINESS_TRAVEL")

    def test_regex_entity_parser(self):
        # Test entity parsing from a mock electricity bill text
        mock_ocr = (
            "Invoice From: Tata Power Grid Co.\n"
            "Invoice Date: 2026-05-25\n"
            "Meter Account Number: ACCT-88214\n"
            "Usage Quantity Billed: 12,450.50 kWh\n"
            "Total Amount Due: $1,245.00"
        )
        
        parsed = extract_entities(mock_ocr)
        self.assertEqual(parsed["quantity"], Decimal("12450.50"))
        self.assertEqual(parsed["unit"], "KWH")
        self.assertEqual(parsed["invoice_date"], date(2026, 5, 25))
        self.assertEqual(parsed["vendor"], "Tata Power Grid Co.")
        self.assertEqual(parsed["facility"], "ACCT-88214")
        self.assertEqual(parsed["invoice_amount"], Decimal("1245.00"))

    def test_quantity_normalization(self):
        # 1. Test gallon to liter conversion
        qty, unit = normalize_quantity_by_unit(Decimal("100"), "gal")
        self.assertEqual(qty, Decimal("378.54100"))
        self.assertEqual(unit, "LITERS")

        # 2. Test mile to kilometer conversion
        qty, unit = normalize_quantity_by_unit(Decimal("10"), "miles")
        self.assertEqual(qty, Decimal("16.09340"))
        self.assertEqual(unit, "KM")

    def test_ocr_readability_heuristics(self):
        # 1. Test clean readable text
        text_clean = "Acme Fuel Invoice: 100 liters purchased on 2026-05-25."
        is_readable, warnings = assess_ocr_readability(text_clean)
        self.assertTrue(is_readable)
        self.assertEqual(len(warnings), 0)

        # 2. Test garbage scrambled text
        text_garbage = "%$@#*&^%! #@*$&%^#@ %$#*&^%@#$"
        is_readable, warnings = assess_ocr_readability(text_garbage)
        self.assertFalse(is_readable)
        self.assertGreater(len(warnings), 0)


class DocumentIngestionAPITests(APITestCase):
    """
    Tests the API layer endpoint POST /api/upload-document/ and duplicate validations.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            name="Demo Organization",
            slug="demo-org"
        )
        self.url = reverse('carbonlens_api:upload_document')

    @patch('carbon_app.views.extract_document_text')
    def test_successful_document_upload_and_persistence(self, mock_ocr_extractor):
        # Mock OCR output text matching electricity bill keywords
        mock_ocr_extractor.return_value = (
            "Invoice From: Tata Power Grid Co.\n"
            "Invoice Date: 2026-05-25\n"
            "Meter Account Number: ACCT-88214\n"
            "Usage Quantity Billed: 25000 kWh\n"
            "Total Amount Due: $2,500.00"
        )

        # Build mock PDF file payload
        pdf_file = SimpleUploadedFile(
            "electricity_bill_q2.pdf",
            b"%PDF-1.4 mock pdf contents",
            content_type="application/pdf"
        )

        response = self.client.post(self.url, {"file": pdf_file}, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["document_type"], "electricity_bill")
        self.assertEqual(response.data["scope_detected"], "SCOPE_2")
        self.assertTrue(response.data["record_created"])

        # Check that DB instances were created and mapped correctly
        job = RawIngestionJob.objects.first()
        self.assertIsNotNone(job)
        self.assertEqual(job.source_type, "DOCUMENT_OCR")
        self.assertEqual(job.status, RawIngestionJob.JobStatus.COMPLETED)

        row = RawDataRow.objects.first()
        self.assertIsNotNone(row)
        self.assertEqual(row.job, job)

        record = EmissionActivityRecord.objects.first()
        self.assertIsNotNone(record)
        self.assertEqual(record.raw_row, row)
        self.assertEqual(record.scope, EmissionActivityRecord.ScopeType.SCOPE_2)
        self.assertEqual(record.category, "PURCHASED_ELECTRICITY")
        self.assertEqual(record.original_quantity, Decimal("25000.0"))
        self.assertEqual(record.plant_facility_code, "ACCT-88214")
        self.assertEqual(record.review_status, EmissionActivityRecord.ReviewStatus.PENDING)

        # Verify AuditLog was auto-triggered on save
        audit = AuditLog.objects.first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.action, AuditLog.ActionType.CREATE)
        self.assertEqual(audit.record_id, record.id)

    @patch('carbon_app.views.extract_document_text')
    def test_duplicate_upload_detection_warnings(self, mock_ocr_extractor):
        # Create an existing record matching identical details
        job = RawIngestionJob.objects.create(
            organization=self.org,
            source_type="DOCUMENT_OCR"
        )
        row = RawDataRow.objects.create(
            organization=self.org,
            job=job,
            payload={},
            row_index=1
        )
        EmissionActivityRecord.objects.create(
            organization=self.org,
            raw_row=row,
            scope=EmissionActivityRecord.ScopeType.SCOPE_2,
            category="PURCHASED_ELECTRICITY",
            original_quantity=Decimal("25000.0"),
            original_unit="KWH",
            normalized_quantity=Decimal("25000.0"),
            normalized_unit="kWh",
            transaction_date=date(2026, 5, 25),
            plant_facility_code="ACCT-88214"
        )

        # Now upload the identical invoice document text
        mock_ocr_extractor.return_value = (
            "Invoice From: Tata Power Grid Co.\n"
            "Invoice Date: 2026-05-25\n"
            "Meter Account Number: ACCT-88214\n"
            "Usage Quantity Billed: 25000 kWh\n"
            "Total Amount Due: $2,500.00"
        )

        pdf_file = SimpleUploadedFile(
            "electricity_bill_dup.pdf",
            b"%PDF-1.4 mock pdf contents",
            content_type="application/pdf"
        )

        response = self.client.post(self.url, {"file": pdf_file}, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        # Verify that a duplicate warning is returned in warnings list
        self.assertTrue(any("duplicate" in w.lower() for w in response.data["warnings"]))

    def test_unsupported_file_format_returns_bad_request(self):
        text_file = SimpleUploadedFile(
            "notes.txt",
            b"unsupported text content",
            content_type="text/plain"
        )
        response = self.client.post(self.url, {"file": text_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("Unsupported file format", response.data["error"])
