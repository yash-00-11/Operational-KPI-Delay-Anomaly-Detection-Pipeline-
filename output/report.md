# Operations anomaly report

Rule: |z| >= 2.0 and |change| >= 20% vs trailing 7-day baseline.

## 2026-10-17: Shipment volume (High)

Shipment volume dropped 48% below its 7-day baseline on Oct 17 (611.0 vs. a typical 1,175.0 orders/day, 8.4 standard deviations from normal). Severity: High. Fewer orders left the warehouse than normal. This usually points to a dock or labor shortfall, a warehouse system problem, or a gap in inbound stock. If it persists, expect an order backlog and late deliveries.

## 2026-10-25: Distribution delay (Critical)

Distribution delay spiked 129% above its 7-day baseline on Oct 25 (13.9 vs. a typical 6.1 hrs, 18.3 standard deviations from normal). Severity: Critical. Shipments are taking much longer to clear the distribution network. Likely causes are carrier capacity limits, sorting backlogs or weather. Expect missed delivery promises and more customer contacts.

## 2026-11-02: Customer complaints (Critical)

Customer complaints spiked 230% above its 7-day baseline on Nov 02 (119.3 vs. a typical 36.1 tickets/day, 24.1 standard deviations from normal). Severity: Critical. Customers are reporting problems at a much higher rate. This typically follows late, damaged or missing deliveries and puts refund and retention at risk.

## Rule comparison

- z-score alone would raise 18 alerts
- percent change alone would raise 6 alerts
- dual threshold raises 3 alerts
