# SDD Specification: Carbon accounting Ingestion & Ledger Optimizations

This specification outlines the advanced carbon accounting features to optimize the Breathe ESG platform to an elite, enterprise-grade audit ledger.

## 1. Feature 1: Plant Registration & Automated Retroactive Re-calculation
- **Problem**: When SAP CSVs contain unknown plant codes, records are ingested with default parameters and flagged as `SUSPICIOUS`. Currently, registering the plant requires manual database inserts, and existing suspicious records do not automatically update.
- **Specification**:
  - Add a **"Register Plant"** action in the UI drawer for any record with an unknown plant warning.
  - Implement a backend `/api/v1/plants/` endpoint (already existing via standard ModelViewSet, but needs handling) and a custom action `/api/v1/records/recalculate_for_plant/` that queries all `NormalizedEmissionRecord`s with draft status containing `Unknown Plant (WERKS)` matching the newly registered plant code.
  - Recalculate their emissions using the newly configured plant's region grid factors and transition their status from `SUSPICIOUS` back to `DRAFT` (or `APPROVED`), resetting the warning.
  - Log an audit trail entry for each modified record: `"Plant code 'WERKS' registered. Retroactive emissions re-calculated."`

## 2. Feature 2: Visual Audit Trail with Before/After Diff Block Styling
- **Problem**: The timeline ledger prints a raw JSON string of before/after changes, making it difficult for financial auditors to read.
- **Specification**:
  - Replace the raw JSON display in the timeline with a parsed, styled diff view.
  - For numeric overrides (e.g., quantity changes), show a neat indicator:
    `Quantity: [Old Quantity] [Unit] -> [New Quantity] [Unit]` (colored red/green).
  - For status changes, show a visual badge transition.

## 3. Feature 3: Live Ingest Error Center & Re-ingest Tool
- **Problem**: Malformed rows inside uploaded CSVs (e.g., text instead of number for consumption) fail hard validation and are staged inside `RawIngestedRecord` with status `FAILED_VALIDATION`. There is currently no UI to view or correct these.
- **Specification**:
  - Add a sub-panel inside the Ingest Center: **"Ingestion Sandbox & Validation Diagnostics"**.
  - Query all `RawIngestedRecord` instances that have `FAILED_VALIDATION` for the organization.
  - Display them in a table alongside their `validation_errors`.
  - Provide a quick inline correction modal where analysts can fix the data (e.g. typing a valid number or date) and click **"Retry Ingestion"** to process the row without having to re-upload the entire CSV!

## 4. Feature 4: Live Data Quality Scorecard & Analytics
- **Problem**: Analysts need a quick visual reading of how audited, high-deviance, or suspicious their overall dataset is.
- **Specification**:
  - Add a premium **"Data Quality & Audit Readiness"** meter on the main dashboard.
  - Compute a score from `0` to `100` calculated as:
    $$\text{Score} = 100 \times \left( \frac{\text{Audited Records} \times 1.0 + \text{Approved Records} \times 0.8 + \text{Draft Records} \times 0.5 - \text{Suspicious Records} \times 0.2}{\text{Total Records}} \right)$$
    (bounded between 0 and 100).
  - Display interactive suggestions (e.g., *"3 plant code warnings remain. Click here to map them."*).
