# Deployment Record: checkout 2.4.1

## Deployment metadata

| Field | Value |
| --- | --- |
| Service | checkout |
| Version | 2.4.1 |
| Deployment type | Configuration correction |
| Database schema migration | No |

## Changes

- Restored the PostgreSQL connection-pool idle timeout from 5 seconds to 120 seconds.
- Kept the payment authorization request timeout at 3 seconds.
- Did not include a database schema migration.

## Verification

Compare checkout p95 latency, connection recreation rate, and PostgreSQL active connections before and after the rollout.
