# Runbook: Checkout Latency Investigation

## Trigger

Use this runbook when:

- checkout API p95 latency exceeds 800 ms for 10 consecutive minutes, or
- checkout API error rate exceeds 1% for 5 consecutive minutes.

## Initial investigation

1. Check whether a `checkout` deployment occurred within the previous 60 minutes.
2. Compare checkout request count, p50/p95 latency, and error rate before and after the deployment.
3. Check payment-provider latency and payment authorization failures.
4. Check PostgreSQL CPU utilization, active connections, slow queries, and connection-pool usage.
5. Check Redis memory usage, eviction count, cache hit rate, and command latency.
6. Check downstream `catalog` and `orders` service latency.

## Common causes

| Signal | Likely cause | First action |
|---|---|---|
| Latency rises immediately after a checkout deployment | Application regression or configuration change | Compare release configuration and prepare rollback decision |
| Payment latency is high | External payment-provider degradation | Activate payment-provider incident process |
| PostgreSQL active connections exceed 80% of configured limit | Connection-pool exhaustion | Inspect pool configuration and slow queries |
| Redis eviction count rises | Insufficient memory or poor cache-key TTL policy | Inspect eviction policy and recent cache changes |
| Orders latency rises with checkout latency | Downstream orders-service degradation | Investigate orders service before rolling back checkout |

## Escalation

- Escalate to the Checkout Team after 10 minutes of sustained SLO breach.
- Escalate to the Database On-Call if PostgreSQL connection use exceeds 80%.
- Escalate to the Payments Team if payment-provider latency exceeds 500 ms.

## Safety

This runbook is investigation guidance only. Do not restart services, change AWS resources, or roll back deployments without explicit human approval.