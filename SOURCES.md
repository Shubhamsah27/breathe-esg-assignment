# Ingestion Source Research & Analysis (`SOURCES.md`)

This document outlines the real-world formatting research conducted for the three carbon accounting data sources, explains the fabricated sample datasets, and details what would break in a production deployment and how to harden it.

---

## 1. SAP Fuel & Procurement Data

### Real-World Format Research
In enterprise environments, SAP fuel issues and materials procurement are typically exported as flat files (e.g. from transaction `SE16` or `MB51`) or integrated via OData BAPIs. In almost all cases, columns use technical abbreviations or German-centric terms:
* `WERKS` (Werk/Plant): The physical plant code. Plant codes mean nothing without a company plant directory lookup.
* `BUDAT` (Buchungsdatum): The posting date in the document.
* `MENGE` (Menge): The quantity.
* `MEINS` (Einheit): Base unit of measure (e.g. `TO` [Tonnes], `L` [Liters]).
* `TXT50` (Materialkurztext): The material short description in German or English (e.g., `"HEIZOEL LEICHT"` [Light Heating Oil], `"DIESELKRAFTSTOFF"` [Diesel]).
* `WRBTR` (Wert in Hauswährung): Value in local currency.
* `WAERS` (Währung): Local currency code (e.g., `EUR`, `USD`).

### Fabricated Sample Explanation
We designed our sample SAP file to mimic this reality. It includes:
* Mixed date formats (`YYYYMMDD` and `DD.MM.YYYY`).
* Inconsistent units (using standard Liters `L` but also mass Tonnes `TO` which the conversion engine must translate based on fuel density).
* European decimal/thousands indicators (`2.500,00` instead of `2500.00`).
* **Anomalies**: Includes plant `"9999"` which represents an unregistered plant, and a transaction with `45,000 TO` which represents a huge, suspicious outlier.

### Production Vulnerabilities & Hardening
* **What would break**: If a client uploads a multi-gigabyte SAP export, Django's memory limit would crash trying to parse the CSV at once.
* **Hardening Strategy**: In production, parse files using a **streaming chunked reader** (e.g. `pandas.read_csv(chunksize=...)`) or load rows asynchronously via **Celery background tasks**, saving raw rows directly to PostgreSQL staging and updating the batch status progressively.

---

## 2. Utility Electricity Data

### Real-World Format Research
Utility portals (such as PG&E, National Grid, or ConEd) allow commercial customers to download historical billing records. 
* Column headers include `Utility Account`, `Meter Number`, `Bill Start Date`, `Bill End Date`, `Consumption`, and `Unit` (often `kWh`, but sometimes `Wh` or `MWh` for huge industrial sites).
* The primary accounting issue is **Billing Cycle Mismatch**: billing cycles do not align with calendar months and often span across month boundaries (e.g. April 12 to May 14).
* The service period can also vary from 28 to 45 days.

### Fabricated Sample Explanation
Our sample utility CSV simulates:
* Standard billing ranges spanning multi-month boundaries.
* Diverse units (`kWh` and `MWh`).
* **Anomalies**: Includes a billing period that spans 61 days (highly abnormal, typical is ~30 days), alerting the analyst to potential duplicate readings or missed billing cycles.

### Production Vulnerabilities & Hardening
* **What would break**: If a meter has multiple overlapping bill dates (e.g., two bills uploaded covering April 1 to April 30), it would double-count consumption.
* **Hardening Strategy**: Build a **Meter Billing Calendar Collision Index**. Ensure that for each physical meter, a unique constraint checks that billing periods do not overlap. If an overlap occurs, reject the upload and flag a duplicate warning.

---

## 3. Corporate Travel Data

### Real-World Format Research
Platforms like Concur or Navan expose travel transactions via REST API endpoints returning JSON payloads. 
* Travel is categorized into flights, hotels, and ground transport.
* For flights, distance is rarely given; instead, only IATA airport codes (`JFK`, `LHR`) and cabin classes (`economy`, `business`) are returned.
* For hotels, durations (nights) and locations are given.
* For ground transport, distance is given alongside vehicle type (train, taxi, rental car).

### Fabricated Sample Explanation
Our simulator accepts JSON payloads mapping these structures:
* Origin/Destination codes (`DEL`, `SFO`).
* Hotel stay country codes (`US`, `DE`).
* Ground transport parameters.
* **Anomalies**: Includes flight cabin `"super_first"` (unknown cabin class, falling back to economy with a warning) and hotel stay country `"XY"` (unknown country, defaulting to global average and flagging warning).

### Production Vulnerabilities & Hardening
* **What would break**: If a traveler books a flight with a typo in the airport code (e.g. `"XCX"` which doesn't exist), the Haversine calculator would fail due to missing latitude/longitude coordinates.
* **Hardening Strategy**: Implement an **automated external coordinates lookup**. If an airport code is missing in the database, fetch its coordinates from an open global aviation API (e.g. OpenFlights) and cache it dynamically, falling back to global average default values only if all external calls time out.
