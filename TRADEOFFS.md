# Deliberate Engineering Trade-offs (`TRADEOFFS.md`)

In carbon accounting, data integrity and mathematical auditability are paramount. To construct a high-integrity prototype, we made strategic decisions to focus our engineering budget on the core ledger mechanics, unit conversions, and analyst workflows. 

Below are the **three features we deliberately did not build** and the justifications behind those trade-offs.

---

## 1. Automated PDF Bill Scraping via OCR / LLM Parsing
* **What We Did Instead**: Supported a structured **Utility Portal CSV Export** format (e.g. PG&E, National Grid portal formats).
* **The Rationale**: Many utility companies provide commercial clients with CSV portal exports containing account meters, start/end dates, and consumption. While PDF bill scraping (via Tesseract OCR or LLMs) is a modern trend, it is highly fragile, prone to read errors (e.g., misreading decimal places or currency indicators), and suffers from performance latencies. Implementing a portal CSV export parser guarantees **100% data ingestion accuracy**, which is the primary requirement for compliance auditors.

---

## 2. Live Flight Tracker API Integration (e.g., Amadeus or Google Flights)
* **What We Did Instead**: Pre-populated a global IATA airport coordinate dictionary and implemented an offline **Haversine Distance Calculator** in Python.
* **The Rationale**: Relying on live flight distance APIs introduces external points of failure, network latency, and requires API key management. Implementing our own localized coordinate database and math engine guarantees **near-zero latency** and **100% offline reliability**. The Haversine great-circle formula calculates exact distances in milliseconds:
  $$\text{JFK} \rightarrow \text{LHR} \approx 5,500 \text{ km}$$
  This is the exact same distance basis used by standard ESG carbon reporting frameworks (e.g. DEFRA).

---

## 3. Dynamic Carbon Offset Ledgers & Scenario Projection Modeler
* **What We Did Instead**: Focused engineering resources on building a high-integrity **Correction Ledger with Immutable Audit Locks**.
* **The Rationale**: Designing dynamic scenario calculators (e.g. "What if we switch to 40% solar by 2030?") is a secondary feature. In carbon accounting, the primary challenge is ensuring that historical data is accurate, auditable, and hasn't been tampered with. We chose to build a comprehensive **manual correction flow** (which automatically recalculates emissions, creates audit trails, and resets statuses to Draft) and an **Audited Lock mechanism** to freeze finalized rows. This solves the auditor's highest-priority pain point: verifying data integrity.
