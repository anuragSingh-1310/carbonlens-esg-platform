from rest_framework import serializers
from .models import RawIngestionJob, EmissionActivityRecord, RawDataRow, AuditLog

class RawIngestionJobSerializer(serializers.ModelSerializer):
    """
    Serializes ingestion jobs. Provides read-only visibility for status,
    uploaded_by, metadata, and error summaries.
    """
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True)

    class Meta:
        model = RawIngestionJob
        fields = [
            'id',
            'source_type',
            'status',
            'uploaded_by',
            'uploaded_by_email',
            'error_summary',
            'metadata',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'status', 'uploaded_by', 'error_summary', 'metadata', 'created_at', 'updated_at']


class IngestionUploadSerializer(serializers.Serializer):
    """
    Form serializer representing the API schema for file uploads.
    """
    source_type = serializers.ChoiceField(choices=RawIngestionJob.SourceType.choices)
    file = serializers.FileField(help_text="CSV or JSON source file matching the type criteria")


class EmissionActivityRecordSerializer(serializers.ModelSerializer):
    """
    Serializes emissions activity records.
    Ensures that once a record is marked as APPROVED, it cannot be modified
    in any way to maintain historical audit compliance.
    """
    approved_by_email = serializers.EmailField(source='approved_by.email', read_only=True)

    class Meta:
        model = EmissionActivityRecord
        fields = [
            'id',
            'raw_row',
            'scope',
            'category',
            'original_quantity',
            'original_unit',
            'normalized_quantity',
            'normalized_unit',
            'transaction_date',
            'plant_facility_code',
            'review_status',
            'anomaly_flag_reason',
            'approved_by',
            'approved_by_email',
            'approved_at',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id', 
            'raw_row', 
            'organization', 
            'normalized_quantity', 
            'normalized_unit', 
            'approved_by', 
            'approved_at', 
            'created_at', 
            'updated_at'
        ]

    def validate(self, attrs):
        """
        Compliance guard: Blocks any updates to an already APPROVED record.
        """
        if self.instance and self.instance.review_status == EmissionActivityRecord.ReviewStatus.APPROVED:
            raise serializers.ValidationError(
                "This record has already been approved and audited. Approved records are strictly immutable."
            )
        return attrs
