import math
import csv
import json
import re
from datetime import datetime, timedelta
from django.utils.dateparse import parse_date
from .models import (
    PlantLookup, AirportLookup, NormalizedEmissionRecord, 
    RawIngestedRecord, AuditLog, IngestionBatch
)

# Global Pre-populated Airport Coordinates for Distance Math (Haversine)
AIRPORT_COORDINATES = {
    'JFK': {'name': 'John F. Kennedy Intl, New York', 'lat': 40.6397, 'lon': -73.7789},
    'LHR': {'name': 'London Heathrow, London', 'lat': 51.4700, 'lon': -0.4543},
    'CDG': {'name': 'Charles de Gaulle, Paris', 'lat': 49.0097, 'lon': 2.5478},
    'SIN': {'name': 'Changi Airport, Singapore', 'lat': 1.3644, 'lon': 103.9915},
    'DXB': {'name': 'Dubai International, Dubai', 'lat': 25.2532, 'lon': 55.3657},
    'FRA': {'name': 'Frankfurt Airport, Frankfurt', 'lat': 50.0379, 'lon': 8.5622},
    'AMS': {'name': 'Amsterdam Schiphol, Amsterdam', 'lat': 52.3105, 'lon': 4.7683},
    'HND': {'name': 'Haneda Airport, Tokyo', 'lat': 35.5523, 'lon': 139.7797},
    'SYD': {'name': 'Kingsford Smith, Sydney', 'lat': -33.9461, 'lon': 151.1772},
    'SFO': {'name': 'San Francisco International, SF', 'lat': 37.6190, 'lon': -122.3749},
    'LAX': {'name': 'Los Angeles International, LA', 'lat': 33.9416, 'lon': -118.4085},
    'ORD': {'name': 'O\'Hare International, Chicago', 'lat': 41.9742, 'lon': -87.9073},
    'DEL': {'name': 'Indira Gandhi Intl, Delhi', 'lat': 28.5562, 'lon': 77.1000},
    'BOM': {'name': 'Chhatrapati Shivaji, Mumbai', 'lat': 19.0896, 'lon': 72.8656},
    'BLR': {'name': 'Kempegowda Intl, Bengaluru', 'lat': 13.1986, 'lon': 77.7068},
    'EWR': {'name': 'Newark Liberty, Newark', 'lat': 40.6925, 'lon': -74.1686},
    'IHA': {'name': 'Houston Intercontinental, Houston', 'lat': 29.9802, 'lon': -95.3397},
}

# Standard Carbon Emission Factors
EMISSION_FACTORS = {
    # Scope 1: Fuels (kg CO2e per normalized unit)
    # Normalized units: Liters for liquid fuels, Cubic Meters for Natural Gas
    'DIESEL': {'factor': 2.68, 'unit': 'L'}, 
    'HEIZOEL': {'factor': 2.68, 'unit': 'L'}, # Light Heating Oil / fuel oil
    'GASOLINE': {'factor': 2.31, 'unit': 'L'}, 
    'NATURAL_GAS': {'factor': 2.02, 'unit': 'm3'}, # Erdgas
    
    # Scope 2: Grid Electricity (kg CO2e per kWh)
    'GRID_ELECTRICITY': {
        'DE': 0.38, # Germany
        'US': 0.37, # USA
        'IN': 0.71, # India
        'UK': 0.21, # United Kingdom
        'DEFAULT': 0.40, # Global Average
    },
    
    # Scope 3: Travel - Flights (kg CO2e per passenger-km)
    'FLIGHT': {
        # Short Haul (< 500 km)
        'SHORT_ECONOMY': 0.15,
        'SHORT_BUSINESS': 0.22,
        # Long Haul (>= 500 km)
        'LONG_ECONOMY': 0.102,
        'LONG_BUSINESS': 0.29,
        'LONG_FIRST': 0.38,
    },
    
    # Scope 3: Travel - Hotels (kg CO2e per room-night)
    'HOTEL': {
        'US': 15.4,
        'DE': 12.8,
        'UK': 10.4,
        'IN': 20.1,
        'SG': 18.5,
        'AE': 22.0,
        'DEFAULT': 15.0,
    },
    
    # Scope 3: Travel - Ground Transport (kg CO2e per km)
    'GROUND': {
        'TAXI': 0.18,
        'TRAIN': 0.04,
        'CAR_RENTAL': 0.17,
        'DEFAULT': 0.15,
    }
}

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate Great-Circle distance between two points in km."""
    R = 6371.0 # Earth's radius in km
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2.0)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    
    return R * c

def parse_sap_date(date_str):
    """Parse SAP dates (could be YYYYMMDD or DD.MM.YYYY or YYYY-MM-DD)."""
    date_str = str(date_str).strip()
    # YYYYMMDD
    if re.match(r'^\d{8}$', date_str):
        try:
            return datetime.strptime(date_str, '%Y%m%d').date()
        except ValueError:
            pass
    # DD.MM.YYYY
    if re.match(r'^\d{1,2}\.\d{1,2}\.\d{4}$', date_str):
        try:
            return datetime.strptime(date_str, '%d.%m.%Y').date()
        except ValueError:
            pass
    # YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    return None

def clean_sap_quantity(quantity_str):
    """Clean European or standard number formats (e.g. 1.500,00 -> 1500.0)."""
    q_str = str(quantity_str).strip()
    # European format: periods as thousands, comma as decimal (e.g. 1.250,50)
    if ',' in q_str and '.' in q_str:
        if q_str.find('.') < q_str.find(','):
            q_str = q_str.replace('.', '').replace(',', '.')
    elif ',' in q_str:
        # Check if comma is decimal (e.g. 25,4)
        parts = q_str.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            q_str = q_str.replace(',', '.')
        else:
            q_str = q_str.replace(',', '')
    
    try:
        return float(q_str)
    except ValueError:
        return 0.0

def normalize_sap_unit(unit_str, description):
    """Normalize SAP units to standard metrics."""
    u = str(unit_str).strip().upper()
    desc = str(description).upper()
    
    # Gas materials
    if 'GAS' in desc:
        if u in ['M3', 'CBM', 'M³']:
            return 1.0, 'm3'
        return 1.0, 'm3' # default
        
    # Liquid fuels
    if u in ['L', 'LIT', 'LTR', 'LITERS', 'LITER']:
        return 1.0, 'L'
    if u in ['TO', 'T', 'TON', 'TONS', 'TONNES']:
        # Convert tonnes of diesel/oil to liters (approx density 0.84 kg/L -> 1 Ton = 1190 L)
        return 1190.0, 'L'
    if u in ['KG', 'KILOGRAM', 'KGS']:
        # 1 kg = 1.19 L approx
        return 1.19, 'L'
        
    return 1.0, u

def get_sap_fuel_type(description):
    """Determine fuel type from description."""
    d = str(description).upper()
    if 'DIESEL' in d:
        return 'DIESEL'
    if 'HEIZOEL' in d or 'OIL' in d or 'HEATING' in d:
        return 'HEIZOEL'
    if 'GAS' in d or 'ERDGAS' in d:
        return 'NATURAL_GAS'
    if 'GASOLINE' in d or 'BENZIN' in d:
        return 'GASOLINE'
    return 'DIESEL' # Fallback default

def process_sap_batch(batch):
    """Process a raw SAP CSV file batch."""
    raw_records = batch.raw_records.all()
    parsed_count = 0
    normalized_count = 0
    failed_count = 0
    suspicious_count = 0
    
    for raw in raw_records:
        parsed_count += 1
        data = raw.raw_data
        errors = []
        warnings = []
        
        # Verify core headers are present
        required_cols = ['WERKS', 'BUDAT', 'MENGE', 'MEINS', 'TXT50']
        missing_cols = [col for col in required_cols if col not in data]
        if missing_cols:
            raw.validation_errors = [f"Missing columns: {', '.join(missing_cols)}"]
            raw.status = 'FAILED_VALIDATION'
            raw.save()
            failed_count += 1
            continue
            
        # Parse fields
        plant_code = str(data['WERKS']).strip()
        date_raw = data['BUDAT']
        qty_raw = data['MENGE']
        unit_raw = data['MEINS']
        desc_raw = data['TXT50']
        
        # Check values
        act_date = parse_sap_date(date_raw)
        if not act_date:
            errors.append(f"Invalid date format: {date_raw}")
            
        qty = clean_sap_quantity(qty_raw)
        if qty <= 0:
            errors.append(f"Quantity must be positive: {qty_raw}")
            
        if errors:
            raw.validation_errors = errors
            raw.status = 'FAILED_VALIDATION'
            raw.save()
            failed_count += 1
            continue
            
        # Resolve plant
        plant = PlantLookup.objects.filter(organization=batch.organization, plant_code=plant_code).first()
        is_suspicious = False
        susp_reasons = []
        
        if not plant:
            is_suspicious = True
            susp_reasons.append(f"Unknown Plant Code '{plant_code}'. Ingestion defaulted to Global standards.")
            plant_name = f"Unknown Plant ({plant_code})"
            plant_region = 'DEFAULT'
        else:
            plant_name = plant.name
            plant_region = plant.region
            
        # Normalize quantity and units
        conversion_factor, norm_unit = normalize_sap_unit(unit_raw, desc_raw)
        norm_qty = qty * conversion_factor
        
        # Emission math
        fuel_type = get_sap_fuel_type(desc_raw)
        ef_info = EMISSION_FACTORS.get(fuel_type, EMISSION_FACTORS['DIESEL'])
        co2e = norm_qty * ef_info['factor']
        
        # Anomaly checks
        if norm_qty > 100000.0:
            is_suspicious = True
            susp_reasons.append(f"Extremely high fuel consumption volume detected: {norm_qty} {norm_unit}")
            
        # Store Normalized Record
        rec = NormalizedEmissionRecord.objects.create(
            organization=batch.organization,
            batch=batch,
            raw_record=raw,
            activity_type='SAP_FUEL',
            scope='Scope 1',
            category='Stationary Combustion' if fuel_type in ['HEIZOEL', 'NATURAL_GAS'] else 'Mobile Combustion',
            activity_date=act_date,
            description=f"SAP Ingestion - Plant {plant_code} ({plant_name}) - {desc_raw}",
            raw_quantity=qty,
            raw_unit=unit_raw,
            normalized_quantity=norm_qty,
            normalized_unit=norm_unit,
            co2e_kg=co2e,
            status='SUSPICIOUS' if is_suspicious else 'DRAFT',
            suspicious_reason='; '.join(susp_reasons) if is_suspicious else None
        )
        
        # Save Audit Log
        AuditLog.objects.create(
            organization=batch.organization,
            record=rec,
            action='INGEST',
            comment=f"Ingested from SAP batch {batch.id}. " + ('; '.join(susp_reasons) if is_suspicious else "Successfully parsed and normalized.")
        )
        
        raw.status = 'NORMALIZED'
        raw.save()
        
        normalized_count += 1
        if is_suspicious:
            suspicious_count += 1
            
    # Update batch summary
    batch.summary = {
        'parsed': parsed_count,
        'normalized': normalized_count,
        'failed': failed_count,
        'suspicious': suspicious_count
    }
    batch.status = 'COMPLETED' if failed_count == 0 else 'COMPLETED' # still complete even if some rows fail validation
    batch.save()


def parse_utility_date(date_str):
    """Parse standard utility portal dates."""
    date_str = str(date_str).strip()
    formats = ['%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', '%d/%m/%Y']
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass
    return None

def normalize_utility_unit(qty, unit_str):
    """Convert Wh / MWh to kWh."""
    u = str(unit_str).strip().upper()
    if u in ['KWH', 'KILOWATT-HOUR', 'KILOWATT HOURS']:
        return qty, 'kWh'
    if u in ['WH', 'WATT-HOUR']:
        return qty / 1000.0, 'kWh'
    if u in ['MWH', 'MEGAWATT-HOUR']:
        return qty * 1000.0, 'kWh'
    return qty, u

def process_utility_batch(batch):
    """Process Utility Ingestion Batch with Calendar Proration."""
    raw_records = batch.raw_records.all()
    parsed_count = 0
    normalized_count = 0
    failed_count = 0
    suspicious_count = 0
    
    for raw in raw_records:
        parsed_count += 1
        data = raw.raw_data
        errors = []
        
        # Verify headers
        required_cols = ['Utility Account', 'Meter Number', 'Bill Start Date', 'Bill End Date', 'Consumption', 'Unit']
        missing_cols = [col for col in required_cols if col not in data]
        if missing_cols:
            raw.validation_errors = [f"Missing columns: {', '.join(missing_cols)}"]
            raw.status = 'FAILED_VALIDATION'
            raw.save()
            failed_count += 1
            continue
            
        account = data['Utility Account']
        meter = data['Meter Number']
        start_raw = data['Bill Start Date']
        end_raw = data['Bill End Date']
        qty_raw = data['Consumption']
        unit_raw = data['Unit']
        tariff = data.get('Tariff / Rate Class', 'Commercial')
        region_code = data.get('Region', 'US') # e.g. DE, IN, US
        
        # Parse start and end dates
        start_date = parse_utility_date(start_raw)
        end_date = parse_utility_date(end_raw)
        
        if not start_date or not end_date:
            errors.append(f"Invalid dates: Start={start_raw}, End={end_raw}")
        elif end_date <= start_date:
            errors.append(f"Billing end date ({end_raw}) must be after start date ({start_raw})")
            
        try:
            qty = float(qty_raw)
            if qty <= 0:
                errors.append(f"Consumption must be positive: {qty_raw}")
        except ValueError:
            errors.append(f"Invalid consumption number: {qty_raw}")
            
        if errors:
            raw.validation_errors = errors
            raw.status = 'FAILED_VALIDATION'
            raw.save()
            failed_count += 1
            continue
            
        # Normalize quantity
        norm_qty_total, norm_unit = normalize_utility_unit(qty, unit_raw)
        
        # Grid Emission Factor Lookup
        ef = EMISSION_FACTORS['GRID_ELECTRICITY'].get(region_code, EMISSION_FACTORS['GRID_ELECTRICITY']['DEFAULT'])
        
        # Calendar Proration Algorithm
        # Split consumption proportionally across daily average
        days_total = (end_date - start_date).days
        daily_average = norm_qty_total / days_total
        
        # We need to find which months are spanned and how many days are in each month
        # Let's iterate day by day and count days in each (year, month)
        month_day_counts = {}
        curr_date = start_date
        while curr_date < end_date:
            key = (curr_date.year, curr_date.month)
            month_day_counts[key] = month_day_counts.get(key, 0) + 1
            curr_date += timedelta(days=1)
            
        # For each spanned month, create a prorated NormalizedEmissionRecord
        is_suspicious_total = False
        susp_reasons = []
        if norm_qty_total > 500000.0:
            is_suspicious_total = True
            susp_reasons.append(f"Extremely high utility billing consumption: {norm_qty_total} kWh")
            
        if days_total > 45:
            is_suspicious_total = True
            susp_reasons.append(f"Billing period is abnormally long ({days_total} days). Typical period is 28-33 days.")
            
        for (yr, mn), days_in_month in month_day_counts.items():
            prorated_qty = daily_average * days_in_month
            prorated_co2e = prorated_qty * ef
            month_name = datetime(yr, mn, 1).strftime('%B %Y')
            
            # Use end_date if it is the final billing month, otherwise use the 28th of that calendar month
            from datetime import date
            if mn == end_date.month and yr == end_date.year:
                record_date = end_date
            else:
                record_date = date(yr, mn, 28)
            
            rec = NormalizedEmissionRecord.objects.create(
                organization=batch.organization,
                batch=batch,
                raw_record=raw,
                activity_type='UTILITY_ELECTRICITY',
                scope='Scope 2',
                category='Purchased Electricity',
                activity_date=record_date,
                description=f"Electricity - Account {account}, Meter {meter} - Prorated portion for {month_name} ({days_in_month}/{days_total} days)",
                raw_quantity=qty * (days_in_month / days_total),
                raw_unit=unit_raw,
                normalized_quantity=prorated_qty,
                normalized_unit=norm_unit,
                co2e_kg=prorated_co2e,
                status='SUSPICIOUS' if is_suspicious_total else 'DRAFT',
                suspicious_reason='; '.join(susp_reasons) if is_suspicious_total else None
            )
            
            AuditLog.objects.create(
                organization=batch.organization,
                record=rec,
                action='INGEST',
                comment=f"Ingested and calendar-prorated for {month_name} ({days_in_month} days of {days_total}-day bill)."
            )
            
        raw.status = 'NORMALIZED'
        raw.save()
        normalized_count += 1
        if is_suspicious_total:
            suspicious_count += 1
            
    # Update batch
    batch.summary = {
        'parsed': parsed_count,
        'normalized': normalized_count,
        'failed': failed_count,
        'suspicious': suspicious_count
    }
    batch.status = 'COMPLETED'
    batch.save()


def process_travel_batch(batch, json_payload):
    """Process travel payload (usually JSON, Navan/Concur API format)."""
    parsed_count = 0
    normalized_count = 0
    failed_count = 0
    suspicious_count = 0
    
    # Save raw records as string representation in batch
    try:
        records_list = json_payload if isinstance(json_payload, list) else json_payload.get('bookings', [])
    except Exception as e:
        batch.status = 'FAILED'
        batch.summary = {'error': f"JSON structure invalid: {str(e)}"}
        batch.save()
        return
        
    for index, data in enumerate(records_list):
        parsed_count += 1
        
        # Save raw backup in DB
        raw = RawIngestedRecord.objects.create(
            batch=batch,
            row_index=index + 1,
            raw_data=data
        )
        
        errors = []
        category = data.get('category', '').lower()
        booking_id = data.get('booking_id', f"TRV-{index+1}")
        
        if not category or category not in ['flight', 'hotel', 'ground']:
            errors.append(f"Invalid or missing travel category: {category}")
            raw.validation_errors = errors
            raw.status = 'FAILED_VALIDATION'
            raw.save()
            failed_count += 1
            continue
            
        details = data.get('details', {})
        date_raw = data.get('date', datetime.utcnow().strftime('%Y-%m-%d'))
        act_date = parse_date(date_raw)
        
        if not act_date:
            errors.append(f"Invalid travel date: {date_raw}")
            raw.validation_errors = errors
            raw.status = 'FAILED_VALIDATION'
            raw.save()
            failed_count += 1
            continue
            
        is_suspicious = False
        susp_reasons = []
        description = f"Travel - {category.capitalize()} (ID {booking_id})"
        co2e = 0.0
        norm_qty = 0.0
        norm_unit = ''
        raw_qty = 0.0
        raw_unit = ''
        
        if category == 'flight':
            origin = str(details.get('origin', '')).strip().upper()
            dest = str(details.get('destination', '')).strip().upper()
            cabin = str(details.get('class', 'economy')).strip().lower()
            
            raw_qty = 1.0
            raw_unit = 'flight'
            norm_unit = 'km'
            
            if not origin or not dest:
                errors.append("Flight requires 'origin' and 'destination' airport codes.")
            else:
                # Resolve coordinates
                coord1 = AIRPORT_COORDINATES.get(origin)
                coord2 = AIRPORT_COORDINATES.get(dest)
                
                # Check DB AirportLookup as fallback
                if not coord1:
                    db_airport = AirportLookup.objects.filter(code=origin).first()
                    if db_airport:
                        coord1 = {'lat': db_airport.latitude, 'lon': db_airport.longitude}
                if not coord2:
                    db_airport = AirportLookup.objects.filter(code=dest).first()
                    if db_airport:
                        coord2 = {'lat': db_airport.latitude, 'lon': db_airport.longitude}
                        
                if not coord1 or not coord2:
                    is_suspicious = True
                    # If we don't have coordinates, default to standard transcontinental distance (~6000 km)
                    norm_qty = 5500.0
                    susp_reasons.append(f"Unknown airport codes '{origin}' or '{dest}'. Distance defaulted to standard LHR-JFK (5,500 km).")
                else:
                    norm_qty = calculate_haversine_distance(coord1['lat'], coord1['lon'], coord2['lat'], coord2['lon'])
                    
                # Standard flight factors based on distance and cabin class
                # Cabin fallback
                if cabin not in ['economy', 'business', 'first']:
                    is_suspicious = True
                    susp_reasons.append(f"Unknown cabin class '{cabin}'. Defaulted to economy factor.")
                    cabin = 'economy'
                    
                is_short = norm_qty < 500.0
                if is_short:
                    ef = EMISSION_FACTORS['FLIGHT']['SHORT_BUSINESS'] if cabin == 'business' else EMISSION_FACTORS['FLIGHT']['SHORT_ECONOMY']
                else:
                    if cabin == 'first':
                        ef = EMISSION_FACTORS['FLIGHT']['LONG_FIRST']
                    elif cabin == 'business':
                        ef = EMISSION_FACTORS['FLIGHT']['LONG_BUSINESS']
                    else:
                        ef = EMISSION_FACTORS['FLIGHT']['LONG_ECONOMY']
                        
                co2e = norm_qty * ef
                description = f"Flight - {origin} to {dest} ({cabin.capitalize()}) - Distance {int(norm_qty)} km"
                
                if norm_qty > 18000.0:
                    is_suspicious = True
                    susp_reasons.append(f"Calculated flight distance is abnormally long: {int(norm_qty)} km. Direct commercial flights do not exceed 16,500 km.")
                    
        elif category == 'hotel':
            country = str(details.get('country', 'US')).strip().upper()
            nights = details.get('nights', 1)
            
            try:
                nights = int(nights)
                if nights <= 0:
                    errors.append("Nights must be positive")
            except ValueError:
                errors.append(f"Invalid nights value: {nights}")
                
            raw_qty = nights
            raw_unit = 'nights'
            norm_qty = nights
            norm_unit = 'room-nights'
            
            if not errors:
                ef = EMISSION_FACTORS['HOTEL'].get(country, EMISSION_FACTORS['HOTEL']['DEFAULT'])
                if country not in EMISSION_FACTORS['HOTEL']:
                    is_suspicious = True
                    susp_reasons.append(f"Unknown hotel country code '{country}'. Defaulted to Global Average hotel emission factor.")
                    
                co2e = nights * ef
                description = f"Hotel Stay - {nights} nights in {country}"
                
                if nights > 30:
                    is_suspicious = True
                    susp_reasons.append(f"Hotel stay duration is abnormally high: {nights} nights.")
                    
        elif category == 'ground':
            transport_type = str(details.get('type', 'DEFAULT')).strip().upper()
            dist_raw = details.get('distance_km', 0.0)
            
            try:
                dist = float(dist_raw)
                if dist <= 0:
                    errors.append("Ground transport distance must be positive")
            except ValueError:
                errors.append(f"Invalid distance: {dist_raw}")
                
            raw_qty = dist_raw
            raw_unit = 'km'
            norm_qty = dist
            norm_unit = 'km'
            
            if not errors:
                ef = EMISSION_FACTORS['GROUND'].get(transport_type, EMISSION_FACTORS['GROUND']['DEFAULT'])
                if transport_type not in EMISSION_FACTORS['GROUND']:
                    is_suspicious = True
                    susp_reasons.append(f"Unknown ground transport type '{transport_type}'. Defaulted to General Ground Transport factor.")
                
                co2e = dist * ef
                description = f"Ground Transport - {transport_type.capitalize()} - {dist} km"
                
                if dist > 1000.0:
                    is_suspicious = True
                    susp_reasons.append(f"Ground transport distance is abnormally high: {dist} km.")
                    
        if errors:
            raw.validation_errors = errors
            raw.status = 'FAILED_VALIDATION'
            raw.save()
            failed_count += 1
            continue
            
        # Store Normalized Record
        rec = NormalizedEmissionRecord.objects.create(
            organization=batch.organization,
            batch=batch,
            raw_record=raw,
            activity_type=f"TRAVEL_{category.upper()}",
            scope='Scope 3',
            category='Category 6: Business Travel',
            activity_date=act_date,
            description=description,
            raw_quantity=raw_qty,
            raw_unit=raw_unit,
            normalized_quantity=norm_qty,
            normalized_unit=norm_unit,
            co2e_kg=co2e,
            status='SUSPICIOUS' if is_suspicious else 'DRAFT',
            suspicious_reason='; '.join(susp_reasons) if is_suspicious else None
        )
        
        # Save Audit Log
        AuditLog.objects.create(
            organization=batch.organization,
            record=rec,
            action='INGEST',
            comment=f"Ingested from Corporate Travel payload. " + ('; '.join(susp_reasons) if is_suspicious else "Successfully parsed.")
        )
        
        raw.status = 'NORMALIZED'
        raw.save()
        normalized_count += 1
        if is_suspicious:
            suspicious_count += 1
            
    # Update batch
    batch.summary = {
        'parsed': parsed_count,
        'normalized': normalized_count,
        'failed': failed_count,
        'suspicious': suspicious_count
    }
    batch.status = 'COMPLETED'
    batch.save()
