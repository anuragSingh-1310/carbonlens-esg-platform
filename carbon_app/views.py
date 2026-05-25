from decimal import Decimal
from django.db import models
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from .models import RawIngestionJob, EmissionActivityRecord
from .serializers import (
    RawIngestionJobSerializer, 
    EmissionActivityRecordSerializer, 
    IngestionUploadSerializer,
    DocumentUploadSerializer
)

import logging
logger = logging.getLogger(__name__)

from .services import (
    validate_uploaded_file,
    extract_document_text,
    classify_document,
    extract_entities,
    check_for_duplicates,
    assess_ocr_readability,
    create_esg_records
)

from rest_framework.response import Response
from rest_framework.decorators import api_view

@api_view(['GET'])
def test_api(request):
    return Response({"message": "CarbonLens API working"})


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination settings for dashboard lists.
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


# ==========================================
# 1. Ingestion Job API
# ==========================================

class IngestionJobAPIView(APIView):
    """
    POST: Uploads a source file (CSV/JSON) and processes it into RawDataRow & EmissionActivityRecord.
    GET: Retrieves the 10 most recent ingestion uploads for the tenant organization.
    """
    permission_classes = []

    def get(self, request, *args, **kwargs):
        from .models import Organization
        org, _ = Organization.objects.get_or_create(
            name="Demo Organization",
            slug="demo-org"
        )
        jobs = RawIngestionJob.objects.filter(
            organization=org
        )[:10]
        serializer = RawIngestionJobSerializer(jobs, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        from .models import Organization
        org, _ = Organization.objects.get_or_create(
            name="Demo Organization",
            slug="demo-org"
        )
        
        serializer = IngestionUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        source_type = serializer.validated_data['source_type']
        uploaded_file = serializer.validated_data['file']
        
        # Extract text content safely from the file wrapper
        try:
            file_content = uploaded_file.read().decode('utf-8')
        except Exception as e:
            return Response(
                {"file": f"Could not read upload payload as a valid UTF-8 string: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        uploaded_by_user = request.user if request.user and request.user.is_authenticated else None
        
        # Initialize ingestion tracking job
        job = RawIngestionJob.objects.create(
            organization=org,
            source_type=source_type,
            status=RawIngestionJob.JobStatus.PENDING,
            uploaded_by=uploaded_by_user,
            metadata={
                "filename": uploaded_file.name, 
                "filesize_bytes": uploaded_file.size
            }
        )
        
        # Invoke parsers synchronously to fit the 4-day MVP architecture
        from .services import (
            ingest_sap_procurement_csv,
            ingest_utility_electricity_csv,
            ingest_corporate_travel_json
        )
        
        if source_type == RawIngestionJob.SourceType.SAP_PROCUREMENT:
            ingest_sap_procurement_csv(org, job, file_content)
        elif source_type == RawIngestionJob.SourceType.UTILITY_ELECTRICITY:
            ingest_utility_electricity_csv(org, job, file_content)
        elif source_type == RawIngestionJob.SourceType.TRAVEL_API:
            ingest_corporate_travel_json(org, job, file_content)
            
        # Reload the job state from DB to return final execution logs
        job.refresh_from_db()
        
        response_serializer = RawIngestionJobSerializer(job)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class DocumentUploadAPIView(APIView):
    """
    POST: Uploads a document (PDF/PNG/JPG/JPEG), runs OCR + image preprocessing,
          classifies the scope/category, extracts key metrics via regex,
          checks for duplicates and low readability, and creates standard ESG records.
    """
    permission_classes = []

    def post(self, request, *args, **kwargs):
        from .models import Organization
        org, _ = Organization.objects.get_or_create(
            name="Demo Organization",
            slug="demo-org"
        )
        
        serializer = DocumentUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"success": False, "error": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        uploaded_file = serializer.validated_data['file']
        filename = uploaded_file.name
        
        try:
            # 1. File Type & Extension checks
            validate_uploaded_file(uploaded_file, filename)
            
            # 2. Extract Text via OCR / pdfplumber
            raw_text = extract_document_text(uploaded_file, filename)
            
            # 3. Classify Document Type & ESG Scope
            doc_type, scope, category, confidence = classify_document(raw_text)
            
            # 4. Extract Structured Entities via Regex
            parsed_data = extract_entities(raw_text)
            
            # 5. Readability / Noise assessment
            is_readable, ocr_warnings = assess_ocr_readability(raw_text)
            
            # 6. Duplicate detection check
            is_duplicate, existing_id = check_for_duplicates(
                org,
                parsed_data["quantity"],
                parsed_data["unit"],
                parsed_data["invoice_date"],
                parsed_data["facility"]
            )
            
            warnings = ocr_warnings.copy()
            if is_duplicate:
                warnings.append(f"Potential duplicate invoice detected. An identical record already exists with ID {existing_id}.")
            
            # 7. Create all relevant multi-tenant database records
            uploaded_by_user = request.user if request.user and request.user.is_authenticated else None
            activity_record = create_esg_records(
                organization=org,
                user=uploaded_by_user,
                filename=filename,
                file_size=uploaded_file.size,
                doc_type=doc_type,
                scope=scope,
                category=category,
                parsed_data=parsed_data,
                raw_text=raw_text
            )
            
            # Formulate structured successful JSON response
            return Response({
                "success": True,
                "document_type": doc_type,
                "scope_detected": scope,
                "extracted_data": {
                    "record_id": activity_record.id,
                    "category": activity_record.category,
                    "original_quantity": float(activity_record.original_quantity),
                    "original_unit": activity_record.original_unit,
                    "normalized_quantity": float(activity_record.normalized_quantity),
                    "normalized_unit": activity_record.normalized_unit,
                    "transaction_date": str(activity_record.transaction_date),
                    "plant_facility_code": activity_record.plant_facility_code,
                    "vendor": parsed_data["vendor"],
                    "invoice_amount": float(parsed_data["invoice_amount"]),
                    "confidence_level": confidence
                },
                "warnings": warnings,
                "record_created": True
            }, status=status.HTTP_201_CREATED)
            
        except RuntimeError as re_err:
            logger.error(f"Runtime configuration error: {str(re_err)}")
            return Response({
                "success": False,
                "error": str(re_err),
                "technical_details": "Tesseract binary missing. System OCR is temporarily offline."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except Exception as e:
            logger.error(f"Universal document ingestion failed: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


# ==========================================
# 2. Dashboard Metrics API
# ==========================================

class DashboardMetricsAPIView(APIView):
    """
    GET: Compiles aggregate analytics and scope distributions for the tenant dashboard.
    """
    permission_classes = []

    def get(self, request, *args, **kwargs):
        from .models import Organization
        org, _ = Organization.objects.get_or_create(
            name="Demo Organization",
            slug="demo-org"
        )
        records = EmissionActivityRecord.objects.filter(organization=org)
        
        # 1. Total and status counts
        total = records.count()
        pending = records.filter(review_status=EmissionActivityRecord.ReviewStatus.PENDING).count()
        flagged = records.filter(review_status=EmissionActivityRecord.ReviewStatus.FLAGGED).count()
        approved = records.filter(review_status=EmissionActivityRecord.ReviewStatus.APPROVED).count()
        
        # 2. Scope Distribution aggregates
        scope_data = records.values('scope').annotate(total_qty=models.Sum('normalized_quantity'))
        scope_distribution = {
            item['scope']: item['total_qty'] or Decimal('0.0') for item in scope_data
        }
        
        # Guarantee fallback keys are present in schema for front-end rendering consistency
        for scope in [EmissionActivityRecord.ScopeType.SCOPE_1, 
                     EmissionActivityRecord.ScopeType.SCOPE_2, 
                     EmissionActivityRecord.ScopeType.SCOPE_3]:
            if scope not in scope_distribution:
                scope_distribution[scope] = Decimal('0.0')
                
        return Response({
            "total_records": total,
            "pending_count": pending,
            "flagged_count": flagged,
            "approved_count": approved,
            "scope_distribution": scope_distribution
        })


# ==========================================
# 3. Activity Records API
# ==========================================

class ActivityRecordListAPIView(generics.ListAPIView):
    """
    GET: Returns a paginated list of EmissionActivityRecords filtered by the organization.
    Filters:
      - review_status (e.g. PENDING, FLAGGED, APPROVED)
      - scope (e.g. SCOPE_1, SCOPE_2, SCOPE_3)
      - source_type (e.g. SAP_PROCUREMENT, UTILITY_ELECTRICITY, TRAVEL_API)
    """
    serializer_class = EmissionActivityRecordSerializer
    permission_classes = []
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        from .models import Organization
        org, _ = Organization.objects.get_or_create(
            name="Demo Organization",
            slug="demo-org"
        )
        # Optimized joined loading for raw row mappings and parent ingestion jobs
        queryset = EmissionActivityRecord.objects.filter(
            organization=org
        ).select_related('raw_row__job', 'approved_by')
        
        # Process filter parameters
        review_status = self.request.query_params.get('review_status')
        if review_status:
            queryset = queryset.filter(review_status=review_status)
            
        scope = self.request.query_params.get('scope')
        if scope:
            queryset = queryset.filter(scope=scope)
            
        source_type = self.request.query_params.get('source_type')
        if source_type:
            queryset = queryset.filter(raw_row__job__source_type=source_type)
            
        return queryset


# ==========================================
# 4. Review Workflow API
# ==========================================

class ActivityRecordReviewAPIView(generics.RetrieveUpdateAPIView):
    """
    PATCH: Allows sustainability analysts to edit pending/flagged records,
    approve them, or add flags.
    Blocks any modifications once the status changes to APPROVED.
    """
    serializer_class = EmissionActivityRecordSerializer
    permission_classes = []
    lookup_field = 'pk'

    def get_queryset(self):
        from .models import Organization
        org, _ = Organization.objects.get_or_create(
            name="Demo Organization",
            slug="demo-org"
        )
        return EmissionActivityRecord.objects.filter(organization=org)

    def perform_update(self, serializer):
        new_status = self.request.data.get('review_status')
        current_user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        
        # Signoff verification logic
        if new_status == EmissionActivityRecord.ReviewStatus.APPROVED:
            serializer.save(
                approved_by=current_user,
                approved_at=timezone.now(),
                current_user=current_user # Pass actor down for the dynamic AuditLog
            )
        else:
            # Clear historical approval attributes if record is downgraded back to pending/flagged
            serializer.save(
                approved_by=None,
                approved_at=None,
                current_user=current_user # Pass actor down for the dynamic AuditLog
            )
        
        # Record edits will trigger pre-save delta comparisons and create an AuditLog automatically
