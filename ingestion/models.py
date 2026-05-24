from django.db import models
from django.contrib.auth.models import User

class Organization(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class PlantLookup(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='plant_lookups')
    plant_code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=100)

    class Meta:
        unique_together = ('organization', 'plant_code')

    def __str__(self):
        return f"{self.plant_code} - {self.name} ({self.region})"

class AirportLookup(models.Model):
    code = models.CharField(max_length=10, unique=True) # e.g. JFK, LHR
    name = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return f"{self.code} - {self.name}"

class IngestionSource(models.Model):
    SOURCE_TYPES = [
        ('SAP', 'SAP ERP Export'),
        ('UTILITY', 'Utility Portal Export'),
        ('TRAVEL', 'Corporate Travel Platform'),
    ]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='sources')
    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_source_type_display()})"

class IngestionBatch(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='batches')
    source = models.ForeignKey(IngestionSource, on_delete=models.CASCADE, related_name='batches')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    filename = models.CharField(max_length=255)
    summary = models.JSONField(default=dict, blank=True) # e.g. {"parsed": 10, "normalized": 8, "failed": 1, "suspicious": 1}
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Batch {self.id} - {self.filename} ({self.status})"

class RawIngestedRecord(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('NORMALIZED', 'Normalized'),
        ('FAILED_VALIDATION', 'Failed Validation'),
    ]
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='raw_records')
    row_index = models.IntegerField()
    raw_data = models.JSONField()
    validation_errors = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    def __str__(self):
        return f"Raw Record {self.id} (Row {self.row_index})"

class NormalizedEmissionRecord(models.Model):
    SCOPE_CHOICES = [
        ('Scope 1', 'Scope 1 (Direct)'),
        ('Scope 2', 'Scope 2 (Indirect Grid)'),
        ('Scope 3', 'Scope 3 (Indirect Value Chain)'),
    ]
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUSPICIOUS', 'Suspicious'),
        ('APPROVED', 'Approved'),
        ('AUDITED', 'Audited'),
    ]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='emission_records')
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='emission_records')
    raw_record = models.ForeignKey(RawIngestedRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name='normalized_record')
    
    activity_type = models.CharField(max_length=50) # e.g. SAP_FUEL, UTILITY_ELECTRICITY, TRAVEL_FLIGHT
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    category = models.CharField(max_length=150) # e.g. Category 6: Business Travel
    activity_date = models.DateField()
    description = models.TextField()
    
    # Original Input Tracking
    raw_quantity = models.FloatField()
    raw_unit = models.CharField(max_length=50)
    
    # Normalized Output Tracking
    normalized_quantity = models.FloatField()
    normalized_unit = models.CharField(max_length=50) # e.g. L, kWh, km
    
    # Footprint
    co2e_kg = models.FloatField()
    
    # Analyst Review state
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    suspicious_reason = models.TextField(blank=True, null=True)
    audit_locked = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Emission Record {self.id} - {self.description} ({self.co2e_kg} kg CO2e)"

class AuditLog(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='audit_logs')
    record = models.ForeignKey(NormalizedEmissionRecord, on_delete=models.CASCADE, related_name='audit_history')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100) # e.g. CREATE, UPDATE, APPROVE, REJECT_SUSPICIOUS, LOCK
    changes = models.JSONField(default=dict, blank=True) # e.g. {"quantity": {"old": 50, "new": 60}}
    comment = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        user_str = self.user.username if self.user else "System"
        return f"{self.action} on Record {self.record_id} by {user_str} at {self.timestamp}"
