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
    IngestionUploadSerializer
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
