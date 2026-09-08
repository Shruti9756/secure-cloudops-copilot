# Runbook: Payment Authorization Latency

## Trigger

Use this runbook when payment authorization latency exceeds 500 ms or the payment provider returns `PAYMENT-GATEWAY-429` responses.

## Investigation

1. Check payment-provider latency, throttling responses, and authorization failure rate.
2. Confirm whether the checkout service is retrying payment authorizations.
3. Escalate to the Payments Team if throttling persists for 10 minutes.

## Safety

This runbook is investigation guidance only. Do not change payment-provider settings without explicit human approval.
