# Breathe ESG - Project Constitution

This document governs the development standards, code quality expectations, design systems, and validation rules for the Breathe ESG Carbon Ingestion & Review platform.

## 1. Core Engineering Principles
- **Predictable Logic over Magic**: Calculations like aviation Haversine distance, daily average proration, and emission factor application must be completely deterministic, deterministic-first, and fully unit-tested.
- **Strict Data Isolation**: Multi-tenant data segregation must be preserved in all endpoints and views by querying objects scoped exclusively by `organization`.
- **Comprehensive Verification**: Any change in core business or mathematical calculations must be matched with dedicated Django backend tests and verified in frontend test scenarios.

## 2. Technical Quality Standards
- **Zero Raw Data Contamination**: Raw imported entries reside in `RawIngestedRecord`. Only fully normalized, successfully computed records may populate `NormalizedEmissionRecord`.
- **Immutable Auditing**: All administrative actions (approvals, flags, manual overrides, locks) must generate a persistent `AuditLog` entry detailing changed fields (before/after states), comments, and timestamps.
- **No Placeholders**: Placeholders, hardcoded stubs, or mock links in critical paths are forbidden. Every feature must be fully functional and ready for ingestion.

## 3. UI/UX & Aesthetic Rules
- **Modern HSL Vanilla CSS**: Keep page layouts visual, immersive, and premium. Use clean HSL CSS tokens, fluid responsive grids, modern typography (Inter/Outfit), and subtle micro-animations (transitions, active node fades).
- **Immediate Actionable Diagnostics**: Validation errors or warnings must never fail silently. They must be highlighted on the ledger with clear warnings and clear options to resolve them in-context.
