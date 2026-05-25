from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class Organization(models.Model):
    """
    Represents the top-level tenant (Enterprise/Corporate Client) in the system.
    All business records must be logically isolated by Organization.
    """
    name = models.CharField(
        max_length=255, 
        unique=True, 
        help_text="The legal name of the organization."
    )
    slug = models.SlugField(
        max_length=255, 
        unique=True, 
        help_text="URL-friendly identifier for routing."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        ordering = ["name"]

    def __str__(self):
        return self.name


class TenantModel(models.Model):
    """
    Abstract base model to enforce consistent multi-tenancy.
    All related tables inherit from this to ensure strict logical isolation.
    Uses PROTECT to avoid accidental deletions of tenant historical data.
    """
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="%(class)ss",
        help_text="The tenant organization associated with this record."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class RawIngestionJob(TenantModel):
    """
    Tracks the lifecycle of an uploaded ingestion payload (CSV, JSON, etc.)
    from external integration touchpoints.
    """
    class SourceType(models.TextChoices):
        SAP_PROCUREMENT = "SAP_PROCUREMENT", "SAP Procurement/Fuel CSV Export"
        UTILITY_ELECTRICITY = "UTILITY_ELECTRICITY", "Utility Electricity CSV Export"
        TRAVEL_API = "TRAVEL_API", "Corporate Travel JSON/API"

    class JobStatus(models.TextChoices):
        PENDING = "PENDING", "Pending Processing"
        PROCESSING = "PROCESSING", "Currently Processing"
        COMPLETED = "COMPLETED", "Completed Successfully"
        FAILED = "FAILED", "Failed Processing"

    source_type = models.CharField(
        max_length=50,
        choices=SourceType.choices,
        help_text="The format/source from which the data originates."
    )
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
        help_text="Current ingestion state."
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ingestion_jobs",
        help_text="User context responsible for initiating the ingestion."
    )
    error_summary = models.TextField(
        null=True,
        blank=True,
        help_text="High-level processing errors or stack trace details if failed."
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Execution metadata (e.g. filename, file size, line counts)."
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.organization.name} | {self.source_type} | {self.status} | {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class RawDataRow(TenantModel):
    """
    Stores raw, unmodified transactional records before normalisation and cleaning.
    Serves as an immutable reference for complete data lineage audits.
    """
    class RowStatus(models.TextChoices):
        UNPROCESSED = "UNPROCESSED", "Unprocessed"
        PROCESSED = "PROCESSED", "Successfully Processed"
        ERROR = "ERROR", "Processing Error"

    job = models.ForeignKey(
        RawIngestionJob,
        on_delete=models.CASCADE,
        related_name="rows",
        help_text="The ingestion job that imported this raw data."
    )
    payload = models.JSONField(
        help_text="Original JSON representation of the imported row before translation."
    )
    row_index = models.PositiveIntegerField(
        help_text="Line/index number of this record inside the raw payload."
    )
    status = models.CharField(
        max_length=20,
        choices=RowStatus.choices,
        default=RowStatus.UNPROCESSED,
        help_text="Processing status of this individual row."
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text="Trace log details if processing of this row failed."
    )

    class Meta:
        ordering = ["job", "row_index"]
        unique_together = (("job", "row_index"),)
        indexes = [
            models.Index(fields=["organization", "status"]),
        ]

    def __str__(self):
        return f"Job {self.job_id} | Row {self.row_index} | {self.status}"


class EmissionActivityRecord(TenantModel):
    """
    The normalized and validated record of an emission-producing activity.
    Fully ready for auditing, reporting, and analytics.
    """
    class ScopeType(models.TextChoices):
        SCOPE_1 = "SCOPE_1", "Scope 1 - Direct Emissions"
        SCOPE_2 = "SCOPE_2", "Scope 2 - Indirect Emissions (Electricity/Purchased Energy)"
        SCOPE_3 = "SCOPE_3", "Scope 3 - Value Chain / Other Indirect"

    class ReviewStatus(models.TextChoices):
        PENDING = "PENDING", "Pending Review"
        FLAGGED = "FLAGGED", "Flagged (Anomaly Detected)"
        APPROVED = "APPROVED", "Approved"

    # Lineage link to raw imported payload
    raw_row = models.OneToOneField(
        RawDataRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_record",
        help_text="Reference to the immutable raw data row for auditing."
    )

    # Classification fields
    scope = models.CharField(
        max_length=10,
        choices=ScopeType.choices,
        help_text="Scope categorization of the activity."
    )
    category = models.CharField(
        max_length=100,
        help_text="Activity category (e.g. Purchased Electricity, Business Flights, Diesel Procurement)."
    )

    # Quantities: stored using DecimalField to eliminate floating-point inaccuracies
    original_quantity = models.DecimalField(
        max_digits=19,
        decimal_places=6,
        help_text="Parsed amount directly from raw upload."
    )
    original_unit = models.CharField(
        max_length=50,
        help_text="Source measurement unit (e.g. Gallons, kWh, passenger-km)."
    )

    normalized_quantity = models.DecimalField(
        max_digits=19,
        decimal_places=6,
        help_text="Amount normalized to the standard unit of measurement."
    )
    normalized_unit = models.CharField(
        max_length=50,
        help_text="Standardized system reporting unit (e.g. kg CO2e, kWh)."
    )

    # Metadata & Date
    transaction_date = models.DateField(
        help_text="Date of physical activity occurrence."
    )
    plant_facility_code = models.CharField(
        max_length=100,
        help_text="Identifier for the local plant, facility, or branch office."
    )

    # Compliance & Review
    review_status = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
        help_text="Current state of review for audit signoff."
    )
    anomaly_flag_reason = models.TextField(
        null=True,
        blank=True,
        help_text="Reason why this row was flagged as an anomaly."
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_records",
        help_text="Auditor who reviewed and signed off on this record."
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of validation signoff."
    )

    class Meta:
        ordering = ["-transaction_date", "id"]
        indexes = [
            models.Index(fields=["organization", "-transaction_date"]),
            models.Index(fields=["organization", "review_status"]),
            # Compound index for facility time-series analysis
            models.Index(fields=["organization", "plant_facility_code", "-transaction_date"]),
        ]

    def __str__(self):
        return f"{self.organization.name} | {self.category} | {self.normalized_quantity} {self.normalized_unit}"

    def clean(self):
        """
        Model-level boundary validations.
        Used to block invalid UI form entry.
        """
        super().clean()
        errors = {}

        if self.original_quantity is not None and self.original_quantity < 0:
            errors['original_quantity'] = "Original quantity cannot be negative."
        if self.normalized_quantity is not None and self.normalized_quantity < 0:
            errors['normalized_quantity'] = "Normalized quantity cannot be negative."

        if errors:
            raise ValidationError(errors)

    def run_anomaly_checks(self):
        """
        Runs business-level heuristic rules on data points.
        Flags anomalous records automatically so that ingestion workflows
        are not broken by validation exceptions.
        """
        reasons = []

        # 1. Negative quantity flag
        if self.original_quantity is not None and self.original_quantity < 0:
            reasons.append(f"Negative original quantity detected ({self.original_quantity})")
        if self.normalized_quantity is not None and self.normalized_quantity < 0:
            reasons.append(f"Negative normalized quantity detected ({self.normalized_quantity})")

        # 2. Heuristic upper thresholds for unrealistic single-transaction spikes
        # Customize these per industrial ESG reporting standards
        LIMITS = {
            "PURCHASED_ELECTRICITY": Decimal("50000000.0"),  # 50,000,000 kWh per entry
            "STATIONARY_FUEL": Decimal("2000000.0"),         # 2,000,000 Liters per entry
            "BUSINESS_TRAVEL": Decimal("200000.0"),          # 200,000 km per trip record
        }

        normal_category = str(self.category).upper().replace(" ", "_")
        upper_limit = LIMITS.get(normal_category, Decimal("10000000.0")) # Fallback baseline threshold

        if self.original_quantity is not None and self.original_quantity > upper_limit:
            reasons.append(
                f"Original quantity {self.original_quantity} exceeds category standard limit ({upper_limit})"
            )
        if self.normalized_quantity is not None and self.normalized_quantity > upper_limit:
            reasons.append(
                f"Normalized quantity {self.normalized_quantity} exceeds maximum expected standard threshold"
            )

        if reasons:
            self.review_status = self.ReviewStatus.FLAGGED
            self.anomaly_flag_reason = " | ".join(reasons)
        else:
            # Revert from FLAGGED to PENDING if corrections are made
            if self.review_status == self.ReviewStatus.FLAGGED:
                self.review_status = self.ReviewStatus.PENDING
                self.anomaly_flag_reason = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Deeply capture pre-save state so we can calculate exact diffs for AuditLog
        self._original_state = self._get_state_dict()

    def _get_state_dict(self):
        if not self.pk:
            return {}
        return {
            "scope": self.scope,
            "category": self.category,
            "original_quantity": str(self.original_quantity) if self.original_quantity else None,
            "original_unit": self.original_unit,
            "normalized_quantity": str(self.normalized_quantity) if self.normalized_quantity else None,
            "normalized_unit": self.normalized_unit,
            "transaction_date": str(self.transaction_date) if self.transaction_date else None,
            "plant_facility_code": self.plant_facility_code,
            "review_status": self.review_status,
            "anomaly_flag_reason": self.anomaly_flag_reason,
            "approved_by_id": self.approved_by_id,
            "approved_at": str(self.approved_at) if self.approved_at else None,
        }

    def save(self, *args, **kwargs):
        """
        Extends saving lifecycle to automatically:
        1. Run robust anomaly heuristics.
        2. Detect differences between pre-save and post-save states.
        3. Write structured change histories to the Tenant Audit Log ledger.
        """
        # Support tracking actor info programmatically
        current_user = kwargs.pop("current_user", None)
        is_new = self.pk is None

        # Execute business anomaly heuristic checks prior to saving
        self.run_anomaly_checks()

        super().save(*args, **kwargs)

        # Audit State Diff Tracking
        changes = {}
        if is_new:
            action = AuditLog.ActionType.CREATE
            for field, val in self._get_state_dict().items():
                changes[field] = [None, val]
        else:
            action = AuditLog.ActionType.UPDATE
            current_state = self._get_state_dict()
            for field, old_val in self._original_state.items():
                new_val = current_state.get(field)
                if old_val != new_val:
                    changes[field] = [old_val, new_val]

            # Detect explicit transitions
            if "review_status" in changes:
                _, new_status = changes["review_status"]
                if new_status == self.ReviewStatus.APPROVED:
                    action = AuditLog.ActionType.APPROVE
                elif new_status == self.ReviewStatus.FLAGGED:
                    action = AuditLog.ActionType.FLAG

        # Avoid redundant audit logs for blank saves
        if is_new or changes:
            AuditLog.objects.create(
                organization=self.organization,
                record_id=self.pk,
                changed_by=current_user,
                action=action,
                changes=changes
            )

        # Sync internal state cache to avoid double entries in multiple saves
        self._original_state = self._get_state_dict()


class AuditLog(models.Model):
    """
    Immutable ledger of state modifications to any EmissionActivityRecord.
    Designed for comprehensive compliance validation during sustainability audits.
    """
    class ActionType(models.TextChoices):
        CREATE = "CREATE", "Emission Record Created"
        UPDATE = "UPDATE", "Emission Record Updated"
        DELETE = "DELETE", "Emission Record Deleted"
        APPROVE = "APPROVE", "Emission Record Signed Off / Approved"
        FLAG = "FLAG", "Emission Record Flagged for Anomaly"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="audit_logs",
        help_text="Tenant context under which the change happened."
    )
    record_id = models.IntegerField(
        help_text="Target primary key of the EmissionActivityRecord (persisted after deletion)."
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_actions",
        help_text="The application user who triggered this change."
    )
    action = models.CharField(
        max_length=20,
        choices=ActionType.choices,
        help_text="The action category executed on the record."
    )
    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text="State changes tracking structure: {'field': [old_value, new_value]}."
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="The timestamp when this transaction occurred."
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["organization", "record_id"]),
            models.Index(fields=["organization", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.organization.slug} | Record {self.record_id} | {self.action} by {self.changed_by or 'System'}"
