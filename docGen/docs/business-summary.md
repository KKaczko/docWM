# Business Summary

This page summarizes configured business processes for non-technical review.

## Order Submission

Receives an order request, validates customer data, creates an invoice, and records that an audit/event publication step is dynamically invoked.


- Owners: Order Management Team, Integration Team
- Tags: order, billing, example
- Entrypoints: `com.example.order:submitOrder`
- Services reached: 3
- External dependencies: 2
- Risks or unknowns: 2

### Business Steps

- Receive request
- Validate customer
- Create invoice

### Key External Dependencies

- `pub.flow:invoke`
- `pub.string:toUpper`
