from django.urls import path
from .views import (
    IngestionJobAPIView,
    DashboardMetricsAPIView,
    ActivityRecordListAPIView,
    ActivityRecordReviewAPIView,
    DocumentUploadAPIView
)

app_name = 'carbonlens_api'

urlpatterns = [
    # Ingestion Job upload & historical monitoring
    path('ingestion/', IngestionJobAPIView.as_view(), name='ingestion_jobs'),
    
    # AI/OCR universal document ingestion
    path('upload-document/', DocumentUploadAPIView.as_view(), name='upload_document'),
    
    # Aggregated dashboard metrics
    path('dashboard/metrics/', DashboardMetricsAPIView.as_view(), name='dashboard_metrics'),
    
    # Paginated ESG records list & filtering
    path('records/', ActivityRecordListAPIView.as_view(), name='activity_records_list'),
    
    # ESG records detail, editing, and approval workflow state changes
    path('records/<int:pk>/review/', ActivityRecordReviewAPIView.as_view(), name='activity_record_review'),
]
