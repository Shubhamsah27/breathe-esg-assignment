import csv
import json
import io
from datetime import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.decorators import action
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User

from .models import (
    Organization, PlantLookup, AirportLookup, IngestionSource, 
    IngestionBatch, RawIngestedRecord, NormalizedEmissionRecord, AuditLog
)
from .serializers import (
    OrganizationSerializer, PlantLookupSerializer, IngestionSourceSerializer, 
    IngestionBatchSerializer, RawIngestedRecordSerializer, NormalizedEmissionRecordSerializer, 
    AuditLogSerializer
)
from .parsers import (
    process_sap_batch, process_utility_batch, process_travel_batch, 
    EMISSION_FACTORS, AIRPORT_COORDINATES
)

class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

class PlantLookupViewSet(viewsets.ModelViewSet):
    queryset = PlantLookup.objects.all()
    serializer_class = PlantLookupSerializer

    def get_queryset(self):
        org_id = self.request.query_params.get('organization')
        if org_id:
            return self.queryset.filter(organization_id=org_id)
        return self.queryset

class IngestionSourceViewSet(viewsets.ModelViewSet):
    queryset = IngestionSource.objects.all()
    serializer_class = IngestionSourceSerializer

    def get_queryset(self):
        org_id = self.request.query_params.get('organization')
        if org_id:
            return self.queryset.filter(organization_id=org_id)
        return self.queryset

class IngestionBatchViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IngestionBatch.objects.all().order_by('-created_at')
    serializer_class = IngestionBatchSerializer

    def get_queryset(self):
        org_id = self.request.query_params.get('organization')
        if org_id:
            return self.queryset.filter(organization_id=org_id)
        return self.queryset

class NormalizedEmissionRecordViewSet(viewsets.ModelViewSet):
    queryset = NormalizedEmissionRecord.objects.all().order_by('-activity_date')
    serializer_class = NormalizedEmissionRecordSerializer

    def get_queryset(self):
        queryset = self.queryset
        org_id = self.request.query_params.get('organization')
        scope = self.request.query_params.get('scope')
        rec_status = self.request.query_params.get('status')
        activity = self.request.query_params.get('activity_type')
        
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        if scope:
            queryset = queryset.filter(scope=scope)
        if rec_status:
            queryset = queryset.filter(status=rec_status)
        if activity:
            queryset = queryset.filter(activity_type=activity)
            
        return queryset

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        record = self.get_object()
        if record.audit_locked:
            return Response({"error": "Record is locked for audit and cannot be modified."}, status=status.HTTP_400_BAD_REQUEST)
            
        user = User.objects.first() # mock user
        
        old_status = record.status
        record.status = 'APPROVED'
        record.save()
        
        AuditLog.objects.create(
            organization=record.organization,
            record=record,
            user=user,
            action='APPROVE',
            changes={"status": {"old": old_status, "new": "APPROVED"}},
            comment=request.data.get('comment', 'Approved by analyst.')
        )
        return Response(NormalizedEmissionRecordSerializer(record).data)

    @action(detail=True, methods=['post'])
    def flag_suspicious(self, request, pk=None):
        record = self.get_object()
        if record.audit_locked:
            return Response({"error": "Record is locked for audit."}, status=status.HTTP_400_BAD_REQUEST)
            
        user = User.objects.first()
        reason = request.data.get('reason', 'Flagged by analyst.')
        
        old_status = record.status
        record.status = 'SUSPICIOUS'
        record.suspicious_reason = reason
        record.save()
        
        AuditLog.objects.create(
            organization=record.organization,
            record=record,
            user=user,
            action='FLAG_SUSPICIOUS',
            changes={"status": {"old": old_status, "new": "SUSPICIOUS"}},
            comment=reason
        )
        return Response(NormalizedEmissionRecordSerializer(record).data)

    @action(detail=False, methods=['post'])
    def bulk_approve(self, request):
        record_ids = request.data.get('record_ids', [])
        org_id = request.data.get('organization')
        
        if not record_ids:
            return Response({"error": "No record_ids provided."}, status=status.HTTP_400_BAD_REQUEST)
            
        records = NormalizedEmissionRecord.objects.filter(id__in=record_ids, audit_locked=False)
        user = User.objects.first()
        
        approved_count = 0
        for rec in records:
            old_status = rec.status
            rec.status = 'APPROVED'
            rec.save()
            
            AuditLog.objects.create(
                organization=rec.organization,
                record=rec,
                user=user,
                action='APPROVE',
                changes={"status": {"old": old_status, "new": "APPROVED"}},
                comment="Bulk approved by analyst."
            )
            approved_count += 1
            
        return Response({"message": f"Successfully approved {approved_count} records."})

    @action(detail=False, methods=['post'])
    def bulk_lock(self, request):
        record_ids = request.data.get('record_ids', [])
        if not record_ids:
            return Response({"error": "No record_ids provided."}, status=status.HTTP_400_BAD_REQUEST)
            
        records = NormalizedEmissionRecord.objects.filter(id__in=record_ids, status='APPROVED')
        user = User.objects.first()
        
        locked_count = 0
        for rec in records:
            rec.status = 'AUDITED'
            rec.audit_locked = True
            rec.save()
            
            AuditLog.objects.create(
                organization=rec.organization,
                record=rec,
                user=user,
                action='LOCK',
                changes={"status": {"old": "APPROVED", "new": "AUDITED"}, "audit_locked": {"old": False, "new": True}},
                comment="Locked and frozen for auditor review."
            )
            locked_count += 1
            
        return Response({"message": f"Successfully locked {locked_count} records for audit."})

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        record = self.get_object()
        
        if record.audit_locked:
            return Response({"error": "Record is locked for audit and cannot be edited."}, status=status.HTTP_400_BAD_REQUEST)
            
        user = User.objects.first()
        
        # Track before state
        old_qty = record.raw_quantity
        old_desc = record.description
        
        # Call super update to save core fields
        serializer = self.get_serializer(record, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Fetch updated record
        record.refresh_from_db()
        new_qty = record.raw_quantity
        
        # If quantity changed, we must recalculate CO2e!
        if old_qty != new_qty:
            # Recalculate co2e proportionally based on previous math or lookup factor
            factor = record.co2e_kg / old_qty if old_qty != 0 else 0.0
            record.co2e_kg = new_qty * factor
            record.normalized_quantity = new_qty # simplified normalization override
            record.status = 'DRAFT' # reset status to draft for re-approval
            record.save()
            
            AuditLog.objects.create(
                organization=record.organization,
                record=record,
                user=user,
                action='EDIT',
                changes={
                    "raw_quantity": {"old": old_qty, "new": new_qty},
                    "co2e_kg": {"old": old_qty * factor, "new": new_qty * factor},
                    "status": {"old": "APPROVED", "new": "DRAFT"}
                },
                comment=request.data.get('comment', 'Quantity manually corrected. Re-calculation performed and status reset to Draft.')
            )
        else:
            AuditLog.objects.create(
                organization=record.organization,
                record=record,
                user=user,
                action='EDIT',
                changes={"description": {"old": old_desc, "new": record.description}},
                comment=request.data.get('comment', 'Record details updated.')
            )
            
        return Response(NormalizedEmissionRecordSerializer(record).data)

class FileUploadView(APIView):
    @method_decorator(csrf_exempt)
    def post(self, request):
        source_id = request.data.get('source_id')
        org_id = request.data.get('organization_id')
        file_obj = request.FILES.get('file')
        
        if not source_id or not org_id or not file_obj:
            return Response({"error": "Missing source_id, organization_id or file"}, status=status.HTTP_400_BAD_REQUEST)
            
        org = get_object_or_404(Organization, id=org_id)
        source = get_object_or_404(IngestionSource, id=source_id, organization=org)
        
        # Create Batch
        batch = IngestionBatch.objects.create(
            organization=org,
            source=source,
            filename=file_obj.name,
            status='PROCESSING'
        )
        
        try:
            # Parse CSV
            csv_file = io.TextIOWrapper(file_obj.file, encoding='utf-8')
            reader = csv.DictReader(csv_file)
            
            raw_records = []
            for idx, row in enumerate(reader):
                raw_records.append(
                    RawIngestedRecord(
                        batch=batch,
                        row_index=idx + 1,
                        raw_data=dict(row)
                    )
                )
                
            RawIngestedRecord.objects.bulk_create(raw_records)
            
            # Run parser engines depending on type
            if source.source_type == 'SAP':
                process_sap_batch(batch)
            elif source.source_type == 'UTILITY':
                process_utility_batch(batch)
                
            return Response({
                "message": "File uploaded and processed successfully.",
                "batch": IngestionBatchSerializer(batch).data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            batch.status = 'FAILED'
            batch.summary = {"error": str(e)}
            batch.save()
            return Response({"error": f"Failed to process file: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TravelIngestionView(APIView):
    @method_decorator(csrf_exempt)
    def post(self, request):
        source_id = request.data.get('source_id')
        org_id = request.data.get('organization_id')
        payload = request.data.get('payload') # list of travel JSON items
        
        if not source_id or not org_id or not payload:
            return Response({"error": "Missing source_id, organization_id, or payload"}, status=status.HTTP_400_BAD_REQUEST)
            
        org = get_object_or_404(Organization, id=org_id)
        source = get_object_or_404(IngestionSource, id=source_id, organization=org)
        
        batch = IngestionBatch.objects.create(
            organization=org,
            source=source,
            filename=f"API_PULL_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
            status='PROCESSING'
        )
        
        try:
            process_travel_batch(batch, payload)
            return Response({
                "message": "Travel bookings payload processed successfully.",
                "batch": IngestionBatchSerializer(batch).data
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            batch.status = 'FAILED'
            batch.summary = {"error": str(e)}
            batch.save()
            return Response({"error": f"Failed to process travel payload: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class DashboardAnalyticsView(APIView):
    def get(self, request):
        org_id = request.query_params.get('organization')
        if not org_id:
            return Response({"error": "organization parameter is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        records = NormalizedEmissionRecord.objects.filter(organization_id=org_id)
        
        # 1. Scope Breakdowns
        scope_summary = records.values('scope').annotate(
            total_co2e=Sum('co2e_kg'),
            count=Count('id')
        )
        
        # 2. Activity Type breakdowns
        activity_summary = records.values('activity_type').annotate(
            total_co2e=Sum('co2e_kg'),
            count=Count('id')
        )
        
        # 3. Status Distributions
        status_summary = records.values('status').annotate(
            count=Count('id')
        )
        
        # 4. Total and Approved/Draft
        totals = records.aggregate(
            total_co2e=Sum('co2e_kg'),
            total_records=Count('id')
        )
        
        # 5. Over Time (trunc by month)
        monthly_summary = records.annotate(
            month=TruncMonth('activity_date')
        ).values('month', 'scope').annotate(
            total_co2e=Sum('co2e_kg')
        ).order_by('month')
        
        # Format monthly data
        monthly_data = {}
        for item in monthly_summary:
            m_str = item['month'].strftime('%Y-%m') if item['month'] else 'Unknown'
            if m_str not in monthly_data:
                monthly_data[m_str] = {'month': m_str, 'Scope 1': 0.0, 'Scope 2': 0.0, 'Scope 3': 0.0, 'total': 0.0}
            sc = item['scope']
            val = item['total_co2e'] or 0.0
            monthly_data[m_str][sc] = val
            monthly_data[m_str]['total'] += val
            
        return Response({
            "total_co2e_kg": totals['total_co2e'] or 0.0,
            "total_records": totals['total_records'] or 0,
            "scopes": {item['scope']: item['total_co2e'] for item in scope_summary},
            "activities": {item['activity_type']: item['total_co2e'] for item in activity_summary},
            "statuses": {item['status']: item['count'] for item in status_summary},
            "monthly_emissions": sorted(monthly_data.values(), key=lambda x: x['month'])
        })

class SeedDatabaseView(APIView):
    def post(self, request):
        """Creates dummy data, lookups, and users to bootstrap review dashboard instantly."""
        # 1. Create Default Organization
        org, _ = Organization.objects.get_or_create(name="Acme Corp Sustainability")
        
        # 2. Create standard plant lookups
        PlantLookup.objects.get_or_create(organization=org, plant_code="1000", name="Munich Assembly Center", region="DE")
        PlantLookup.objects.get_or_create(organization=org, plant_code="1200", name="Berlin Logistics Yard", region="DE")
        PlantLookup.objects.get_or_create(organization=org, plant_code="2000", name="San Jose R&D Center", region="US")
        PlantLookup.objects.get_or_create(organization=org, plant_code="3000", name="Bengaluru Software Lab", region="IN")
        PlantLookup.objects.get_or_create(organization=org, plant_code="4000", name="London Executive Office", region="UK")
        
        # 3. Create pre-populated airport lookups
        for code, details in AIRPORT_COORDINATES.items():
            AirportLookup.objects.get_or_create(
                code=code,
                defaults={
                    'name': details['name'],
                    'latitude': details['lat'],
                    'longitude': details['lon']
                }
            )
            
        # 4. Create Ingestion Sources
        sap_source, _ = IngestionSource.objects.get_or_create(
            organization=org, name="SAP Procurement ERP", source_type="SAP"
        )
        util_source, _ = IngestionSource.objects.get_or_create(
            organization=org, name="PG&E Utility Scraping Portal", source_type="UTILITY"
        )
        travel_source, _ = IngestionSource.objects.get_or_create(
            organization=org, name="Corporate Travel Portal Concur", source_type="TRAVEL"
        )
        
        # 5. Create default auditor user
        user, created = User.objects.get_or_create(username="lead_analyst")
        if created:
            user.set_password("breathe_esg_pass")
            user.save()
            
        return Response({
            "message": "Database seeded successfully!",
            "organization_id": org.id,
            "sources": {
                "SAP": sap_source.id,
                "UTILITY": util_source.id,
                "TRAVEL": travel_source.id
            }
        })
