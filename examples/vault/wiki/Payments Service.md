---
tags: [payments, billing]
aliases: [checkout, billing service]
---
# Payments Service
We chose Stripe over Braintree for the lower international fees.
Retries use idempotency keys; webhooks are verified with the signing secret.
