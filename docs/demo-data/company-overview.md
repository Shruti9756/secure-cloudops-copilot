# NimbusCart Engineering Platform

> This is a fictional e-commerce company created only for SecureCloudOps Copilot demonstrations.

NimbusCart operates an online marketplace. Its critical customer journey is:

Browse products → Add product to cart → Checkout → Payment authorization → Order creation → Customer notification

## Services

| Service | Responsibility | Owner |
|---|---|---|
| storefront | Customer-facing web experience | Web Platform |
| catalog | Product search, price, and availability | Catalog Team |
| checkout | Validates carts and coordinates payment and order creation | Checkout Team |
| payments | Integrates with the external payment provider | Payments Team |
| orders | Persists confirmed orders and exposes order status | Orders Team |
| notifications | Sends order-confirmation emails | Messaging Team |

## Checkout request flow

1. The storefront sends a checkout request to the `checkout` service.
2. `checkout` validates the cart with `catalog`.
3. `checkout` calls `payments` for authorization.
4. `checkout` creates an order through `orders`.
5. `checkout` returns confirmation to the storefront.
6. `notifications` sends an order-confirmation email asynchronously.

## Service objectives

| Metric | Target |
|---|---|
| checkout API p95 latency | Less than 800 ms |
| checkout API error rate | Less than 1% |
| payment authorization success rate | Greater than 98% |
| document-ingestion success rate | Greater than 99% |

## Important operational dependencies

- The `checkout` and `orders` services use PostgreSQL.
- Redis is used for short-lived cart and idempotency data.
- The payment provider is external and can become slow or unavailable.
- Deployments are recorded with service name, version, time, and change summary.
- No production changes may be triggered automatically by an AI assistant.