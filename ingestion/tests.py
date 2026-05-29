from django.test import TestCase
from django.utils.dateparse import parse_date
from datetime import datetime, date
from django.contrib.auth.models import User

from .models import (
    Organization, PlantLookup, AirportLookup, IngestionSource, 
    IngestionBatch, RawIngestedRecord, NormalizedEmissionRecord
)
from .parsers import (
    calculate_haversine_distance, clean_sap_quantity, 
    normalize_sap_unit, process_sap_batch, process_utility_batch, 
    process_travel_batch
)

class CarbonAccountingTests(TestCase):
    def setUp(self):
        # Create Organizations (Tenants)
        self.org_a = Organization.objects.create(name="Tenant A Corp")
        self.org_b = Organization.objects.create(name="Tenant B Corp")

        # Create Lookup Mappings for Tenant A
        PlantLookup.objects.create(organization=self.org_a, plant_code="1000", name="Munich Assembly", region="DE")
        PlantLookup.objects.create(organization=self.org_a, plant_code="2000", name="San Jose Lab", region="US")

        # Create Sources for Tenant A
        self.sap_source = IngestionSource.objects.create(organization=self.org_a, name="SAP ERP", source_type="SAP")
        self.util_source = IngestionSource.objects.create(organization=self.org_a, name="PG&E", source_type="UTILITY")
        self.travel_source = IngestionSource.objects.create(organization=self.org_a, name="Concur", source_type="TRAVEL")

        # Seed global IATA airports
        AirportLookup.objects.create(code="JFK", name="JFK, NY", latitude=40.6397, longitude=-73.7789)
        AirportLookup.objects.create(code="LHR", name="LHR, London", latitude=51.4700, longitude=-0.4543)

        # Create mock analyst
        User.objects.create(username="lead_analyst")

    def test_haversine_formula(self):
        """Test calculation of distance between JFK and LHR (approx 5500 km)."""
        dist = calculate_haversine_distance(40.6397, -73.7789, 51.4700, -0.4543)
        self.assertGreater(dist, 5400)
        self.assertLess(dist, 5600)

    def test_sap_clean_number_format(self):
        """Test that European formatted quantities are cleaned correctly."""
        self.assertEqual(clean_sap_quantity("1.250,50"), 1250.5)
        self.assertEqual(clean_sap_quantity("25,4"), 25.4)
        self.assertEqual(clean_sap_quantity("5000"), 5000.0)

    def test_sap_ingestion_normalization(self):
        """Test SAP fuel ingestion parsing, lookup mapping, and emission calculations."""
        batch = IngestionBatch.objects.create(
            organization=self.org_a,
            source=self.sap_source,
            filename="sap_issues.csv",
            status="PROCESSING"
        )
        
        # Valid Row
        RawIngestedRecord.objects.create(
            batch=batch,
            row_index=1,
            raw_data={"WERKS": "1000", "BUDAT": "20260420", "MENGE": "1500", "MEINS": "L", "TXT50": "DIESEL FUEL"}
        )
        # Unrecognized Plant Row (triggers suspicious anomaly warning)
        RawIngestedRecord.objects.create(
            batch=batch,
            row_index=2,
            raw_data={"WERKS": "9999", "BUDAT": "20260422", "MENGE": "2000", "MEINS": "L", "TXT50": "HEIZOEL LIGHT"}
        )

        process_sap_batch(batch)
        
        # Verify two records created
        records = NormalizedEmissionRecord.objects.filter(batch=batch)
        self.assertEqual(records.count(), 2)
        
        rec1 = records.filter(description__contains="Plant 1000").first()
        self.assertEqual(rec1.status, "DRAFT")
        self.assertEqual(rec1.normalized_quantity, 1500.0)
        self.assertEqual(rec1.normalized_unit, "L")
        # CO2e: 1500 L * 2.68 factor = 4020.0 kg
        self.assertAlmostEqual(rec1.co2e_kg, 4020.0)
        
        rec2 = records.filter(description__contains="Plant 9999").first()
        # Unrecognized plant must be marked SUSPICIOUS!
        self.assertEqual(rec2.status, "SUSPICIOUS")
        self.assertIn("Unknown Plant Code", rec2.suspicious_reason)

    def test_utility_calendar_proration(self):
        """Test that a cross-month utility bill splits consumption proportionally into individual calendar months."""
        batch = IngestionBatch.objects.create(
            organization=self.org_a,
            source=self.util_source,
            filename="pge_bill.csv",
            status="PROCESSING"
        )
        
        # Bill spanning April 15 to May 15 (30 days total), usage 3000 kWh
        RawIngestedRecord.objects.create(
            batch=batch,
            row_index=1,
            raw_data={
                "Utility Account": "90918-202",
                "Meter Number": "MTR-881",
                "Bill Start Date": "2026-04-15",
                "Bill End Date": "2026-05-15",
                "Consumption": "3000",
                "Unit": "kWh",
                "Region": "US"
            }
        )

        process_utility_batch(batch)
        
        # Should generate two prorated records: April portion and May portion
        records = NormalizedEmissionRecord.objects.filter(batch=batch).order_by('activity_date')
        self.assertEqual(records.count(), 2)
        
        # April has 16 days (April 15 to April 30 inclusive) -> 16/30 * 3000 = 1600 kWh
        # May has 14 days (May 1 to May 14 inclusive) -> 14/30 * 3000 = 1400 kWh
        april_rec = records.first()
        self.assertEqual(april_rec.activity_date.month, 4)
        self.assertEqual(april_rec.normalized_quantity, 1600.0)
        self.assertAlmostEqual(april_rec.co2e_kg, 1600.0 * 0.37) # US grid factor 0.37
        
        may_rec = records.last()
        self.assertEqual(may_rec.activity_date.month, 5)
        self.assertEqual(may_rec.normalized_quantity, 1400.0)
        self.assertAlmostEqual(may_rec.co2e_kg, 1400.0 * 0.37)

    def test_multi_tenancy_isolation(self):
        """Test that data belongs strictly to its own Organization tenant."""
        batch_a = IngestionBatch.objects.create(organization=self.org_a, source=self.sap_source, filename="sap.csv")
        batch_b = IngestionBatch.objects.create(organization=self.org_b, source=IngestionSource.objects.create(organization=self.org_b, name="B-SAP", source_type="SAP"), filename="sap.csv")
        
        NormalizedEmissionRecord.objects.create(
            organization=self.org_a, batch=batch_a, activity_type="SAP_FUEL", scope="Scope 1", category="Stationary",
            activity_date=date(2026, 4, 1), description="A-Fuel", raw_quantity=10, raw_unit="L",
            normalized_quantity=10, normalized_unit="L", co2e_kg=26.8
        )
        
        NormalizedEmissionRecord.objects.create(
            organization=self.org_b, batch=batch_b, activity_type="SAP_FUEL", scope="Scope 1", category="Stationary",
            activity_date=date(2026, 4, 1), description="B-Fuel", raw_quantity=20, raw_unit="L",
            normalized_quantity=20, normalized_unit="L", co2e_kg=53.6
        )
        
        # Assert Tenant A sees only A-Fuel
        recs_a = NormalizedEmissionRecord.objects.filter(organization=self.org_a)
        self.assertEqual(recs_a.count(), 1)
        self.assertEqual(recs_a.first().description, "A-Fuel")
        
        # Assert Tenant B sees only B-Fuel
        recs_b = NormalizedEmissionRecord.objects.filter(organization=self.org_b)
        self.assertEqual(recs_b.count(), 1)
        self.assertEqual(recs_b.first().description, "B-Fuel")

    def test_retroactive_plant_recalculation(self):
        """Test registering an unknown plant dynamically updates suspicious records and clears warning."""
        batch = IngestionBatch.objects.create(
            organization=self.org_a,
            source=self.sap_source,
            filename="sap_errors.csv",
            status="PROCESSING"
        )
        raw = RawIngestedRecord.objects.create(
            batch=batch,
            row_index=1,
            raw_data={"WERKS": "9999", "BUDAT": "20260420", "MENGE": "1000", "MEINS": "L", "TXT50": "DIESEL FUEL"}
        )
        
        process_sap_batch(batch)
        
        rec = NormalizedEmissionRecord.objects.filter(batch=batch).first()
        self.assertEqual(rec.status, "SUSPICIOUS")
        self.assertIn("Unknown Plant Code '9999'", rec.suspicious_reason)
        
        # Now register the plant via standard Django or test lookup creation
        PlantLookup.objects.create(organization=self.org_a, plant_code="9999", name="Berlin Gigafactory", region="DE")
        
        # Call the recalculate action via POST or direct function call in Views
        from django.test import RequestFactory
        from .views import NormalizedEmissionRecordViewSet
        
        factory = RequestFactory()
        request = factory.post('/api/v1/records/recalculate_for_plant/', {
            'plant_code': '9999',
            'organization': self.org_a.id
        }, content_type='application/json')
        
        view = NormalizedEmissionRecordViewSet.as_view({'post': 'recalculate_for_plant'})
        response = view(request)
        
        self.assertEqual(response.status_code, 200)
        
        # Fetch updated record
        rec.refresh_from_db()
        self.assertEqual(rec.status, "DRAFT")
        self.assertIsNone(rec.suspicious_reason)
        self.assertIn("Berlin Gigafactory", rec.description)

    def test_staging_sandbox_validation_retry(self):
        """Test correcting a malformed CSV record staged in RawIngestedRecord and retrying via sandbox endpoint."""
        batch = IngestionBatch.objects.create(
            organization=self.org_a,
            source=self.sap_source,
            filename="malformed.csv",
            status="PROCESSING",
            summary={"parsed": 1, "failed": 1, "normalized": 0, "suspicious": 0}
        )
        # Seed record that failed validation because quantity was negative
        raw = RawIngestedRecord.objects.create(
            batch=batch,
            row_index=1,
            raw_data={"WERKS": "1000", "BUDAT": "20260420", "MENGE": "-500", "MEINS": "L", "TXT50": "DIESEL"},
            validation_errors=["Quantity must be positive"],
            status="FAILED_VALIDATION"
        )
        
        # Try view retry action
        from django.test import RequestFactory
        from .views import RawIngestedRecordViewSet
        
        factory = RequestFactory()
        # Correct the quantity to positive 1500
        request = factory.post(f'/api/v1/raw-records/{raw.id}/retry_ingest/', {
            'raw_data': {"WERKS": "1000", "BUDAT": "20260420", "MENGE": "1500", "MEINS": "L", "TXT50": "DIESEL"}
        }, content_type='application/json')
        
        view = RawIngestedRecordViewSet.as_view({'post': 'retry_ingest'})
        response = view(request, pk=raw.id)
        
        self.assertEqual(response.status_code, 200)
        
        raw.refresh_from_db()
        self.assertEqual(raw.status, "NORMALIZED")
        self.assertEqual(raw.validation_errors, [])
        
        # Check that NormalizedEmissionRecord is created
        norm_rec = NormalizedEmissionRecord.objects.filter(raw_record=raw).first()
        self.assertIsNotNone(norm_rec)
        self.assertEqual(norm_rec.raw_quantity, 1500.0)
        self.assertEqual(norm_rec.status, "DRAFT")

