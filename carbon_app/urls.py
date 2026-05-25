from django.urls import path
from .views import (
    IngestionJobAPIView,
    DashboardMetricsAPIView,
    ActivityRecordListAPIView,
    ActivityRecordReviewAPIView
)

app_name = 'carbonlens_api'

urlpatterns = [
    # Ingestion Job upload & historical monitoring
    path('ingestion/', IngestionJobAPIView.as_view(), name='ingestion_jobs'),
    
    # Aggregated dashboard metrics
    path('dashboard/metrics/', DashboardMetricsAPIView.as_view(), name='dashboard_metrics'),
    
    # Paginated ESG records list & filtering
    path('records/', ActivityRecordListAPIView.as_view(), name='activity_records_list'),
    
    # ESG records detail, editing, and approval workflow state changes
    path('records/<int:pk>/review/', ActivityRecordReviewAPIView.as_view(), name='activity_record_review'),
]
