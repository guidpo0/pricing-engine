# Integration Guide

The Pricing Engine was designed as a **zero-latency microservice**, built specifically to isolate complex domain business rules (financial mathematics) away from *Client* applications (such as your main legacy backend, databases, or mobile Apps).

## Single Responsibility Paradigm (Microservices)

1. **Your Main Application (The Client):**
   Your main application does not need to, and should not, know how to interpolate a flat-forward curve or calculate semi-annual coupons. Its sole responsibility is to orchestrate domain models—to know "What" the customer owns. Example: "User Roberto holds 10.51 shares of Tesouro IPCA+ 2035".

2. **The Pricing Engine (This project):**
   This engine centralizes all mutable government rules and live Brazilian financial market rates. Its singular responsibility is to calculate "How much" Roberto's asset is worth precisely today.

The entire Pricing infrastructure can and should scale completely decoupled from your core business application in a Kubernetes/Docker cluster.

---

## How to Consume (Practically)

Whenever your main application needs a user's financial value to render a Dashboard or Daily Balance, it performs a Server-to-Server `POST` HTTP request to our Pricing Engine.

### The Request (Your App ➔ Pricing Engine):
Send only the bond identifier and the exact user fraction holding (`quantity`).
**Endpoint:** `POST /portfolio/value`
```json
{
    "bond_type": "IPCA",
    "maturity_date": "2035-05-15",
    "quantity": 10.51
}
```

### The Response (Pricing Engine ➔ Your App):
The engine injects the in-memory prevailing `IPCA+` yielding curve on the fly, computes the exact elapsed business days, crunches the numbers, and returns the strictly polished data in milliseconds.
```json
{
    "bond_type": "IPCA",
    "maturity_date": "2035-05-15",
    "pu": 4150.25,
    "quantity": 10.51,
    "position_value": 43619.13,
    "yield_rate": 0.0612,
    "vna": 4212.18,
    "calculation_date": "2026-03-08"
}
```

Your system then extracts the `"position_value" (R$ 43,619.13)` node and ships it straight to your Frontend. Your Core Backend team and database never had to write a single piece of logic for pricing a Brazilian bond.
