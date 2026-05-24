from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Organization, PlantLookup, AirportLookup, IngestionSource, 
    IngestionBatch, RawIngestedRecord, NormalizedEmissionRecord, AuditLog
)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = '__all__'

class PlantLookupSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantLookup
        fields = '__all__'

class AirportLookupSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirportLookup
        fields = '__all__'

class IngestionSourceSerializer(serializers.ModelSerializer):
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    
    class Meta:
        model = IngestionSource
        fields = ['id', 'organization', 'name', 'source_type', 'source_type_display', 'created_at']

class IngestionBatchSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source='source.name', read_only=True)
    source_type = serializers.CharField(source='source.source_type', read_only=True)
    
    class Meta:
        model = IngestionBatch
        fields = ['id', 'organization', 'source', 'source_name', 'source_type', 'status', 'filename', 'summary', 'created_at', 'updated_at']

class RawIngestedRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawIngestedRecord
        fields = '__all__'

class AuditLogSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source='user', read_only=True)
    
    class Meta:
        model = AuditLog
        fields = ['id', 'organization', 'record', 'user', 'user_detail', 'action', 'changes', 'comment', 'timestamp']

class NormalizedEmissionRecordSerializer(serializers.ModelSerializer):
    audit_history = AuditLogSerializer(many=True, read_only=True)
    batch_detail = IngestionBatchSerializer(source='batch', read_only=True)
    
    class Meta:
        model = NormalizedEmissionRecord
        fields = [
            'id', 'organization', 'batch', 'batch_detail', 'raw_record', 'activity_type', 
            'scope', 'category', 'activity_date', 'description', 
            'raw_quantity', 'raw_unit', 'normalized_quantity', 'normalized_unit', 
            'co2e_kg', 'status', 'suspicious_reason', 'audit_locked', 
            'created_at', 'updated_at', 'audit_history'
        ]
