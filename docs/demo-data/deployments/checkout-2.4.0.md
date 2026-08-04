# Deployment Record: checkout 2.4.0

## Metadata

| Field | Value |
|---|---|
| Service | checkout |
| Version | 2.4.0 |
| Deployment time | 2026-08-03 21:00 UTC |
| Deployed by | Checkout Team CI/CD pipeline |
| Status | Successful |

## Changes

- Added order-validation logging.
- Changed PostgreSQL connection-pool idle timeout from 120 seconds to 5 seconds.
- Increased payment authorization request timeout from 2 seconds to 3 seconds.
- No database schema migration was included.

## Post-deployment observation

At 21:12 UTC, checkout p95 latency increased from approximately 620 ms to 1,450 ms. Error rate remained below 1%.

## Follow-up hypothesis

The reduced PostgreSQL connection-pool idle timeout may cause frequent connection recreation during periods of sustained checkout traffic. Confirm this by checking active connections, connection creation rate, and database latency.