# Resolved Ambiguities & Decisions (`DECISIONS.md`)

This document outlines the technical ambiguities resolved during development, the specific subsets of data we chose to support, and the strategic questions we would raise to the Product Manager (PM) for a production-ready application.

---

## 1. Ambiguities Resolved

### A. Calendar-Spanning Utility Billing Periods
* **The Ambiguity**: Utility billing cycles rarely align with calendar months (e.g., April 15 to May 15). Carbon reporting auditors, however, expect reports aggregated strictly by calendar month (e.g., April vs. May).
* **The Resolution**: We implemented a **Daily-Average Proration Algorithm**. The parser computes the total days in the billing cycle, calculates a daily consumption average, and divides the consumption proportionally across the spanned calendar months. For each spanned month, a separate `NormalizedEmissionRecord` is generated with its own activity date, ensuring calendar compliance.

### B. Dynamic Flight Distance Calculations
* **The Ambiguity**: Travel API exports (Concur/Navan) contain airport codes (`JFK`, `LHR`) but lack flight distances.
* **The Resolution**: We created a coordinate database for popular global airports inside `parsers.py`. During travel JSON ingestion, the parser looks up the latitudes and longitudes of the departure and arrival airports and applies the **Haversine formula** to calculate the great-circle distance in kilometers:
  $$d = 2R \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)}\right)$$
  This is highly robust, realistic, and offline-capable!

### C. Missing Travel Details & Fallbacks
* **The Ambiguity**: Real-world corporate travel files often miss key details (e.g. seat class for a flight, or hotel country).
* **The Resolution**: Instead of throwing an ingestion error, we implemented **Intelligent Fallbacks with Suspicious Warnings**:
  * If a flight seat class is missing, we default to `economy` and flag the record as `SUSPICIOUS` with the reason `"Missing seat class; defaulted to Economy."`
  * If a hotel country is unknown, we default to the Global Average hotel emission factor (`15.0 kg CO2e / night`) and flag the record as `SUSPICIOUS` with the warning `"Unknown country code; defaulted to Global Average."`

### D. Unknown SAP Plant Codes (`WERKS`)
* **The Ambiguity**: SAP files contain plant codes (e.g. `9999`) that are not yet registered in our client database.
* **The Resolution**: We ingest the record, normalize the quantity, calculate emissions using global defaults, but mark the record's status as `SUSPICIOUS` with the reason `"Unknown Plant Code '9999'. Defaulted regional grid factor to Global Average."` This alerts the analyst to register the plant code mapping without stopping the ingestion pipeline.

---

## 2. Subsets Handled vs. Ignored

### In Scope (Handled)
* **SAP CSV**: Handles standard column abbreviations (`WERKS`, `BUDAT`, `MENGE`, `MEINS`, `TXT50`, `WRBTR`, `WAERS`) and standard SAP date formats (e.g., `YYYYMMDD`, `DD.MM.YYYY`, and `YYYY-MM-DD`). Handles European number formatting (e.g. `2.500,00`).
* **Utility CSV**: Handles `kWh`, `Wh`, and `MWh` unit conversions, proration splits, and regional grid lookup translations.
* **Travel JSON**: Handles Flight seat class emission weights (Short-haul vs. Long-haul Economy/Business/First), Hotel room-night calculations, and Ground transport categories (Taxi, Train, Rental Car).

### Out of Scope (Ignored)
* **Multi-Segment Flights**: We ignored multi-stop layovers for flights. The JSON payload is assumed to contain individual flight legs as single origin-destination pairs.
* **Line-Item Price Discrepancies**: We ignored currency conversions for SAP procurement records. For the prototype, standard emission calculations are derived from mass/volume quantities rather than monetary spend values.
* **Complex Tariff Structures**: We ignored peak vs. off-peak utility tariffs. We aggregate total billed consumption (kWh) and apply average regional grid emissions, which is standard practice in carbon accounting.

---

## 3. What We Would Ask the PM

1. **Voucher Validation Rollbacks**: *"If a file contains 500 rows and 5 of them have severe formatting errors (e.g. negative values or missing columns), should we reject the entire file and roll back the database transaction, or should we ingest the 495 valid rows and write the 5 failed ones to a staging error report?"* (We chose to import the valid rows and write staging error reports to keep client efficiency high).
2. **Plant Code Configurations**: *"Are plant-to-location lookups strictly configured by clients through the UI dashboard, or do we sync them automatically via an SAP OData metadata service?"*
3. **Multi-Role Auditor Approval Workflow**: *"Should the audit lock status support hierarchical approvals (e.g. Junior analyst imports -> Lead analyst flags/approves -> Senior auditor signs-off and locks) or is a single role sufficient?"*
