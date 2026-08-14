# Live Local Reliability Lab

This stack runs the checkout workload, OpenTelemetry Collector, Prometheus, and
Grafana on one Docker network. Telemetry crosses the OpenTelemetry Collector
before Prometheus evaluates the agent-generated alert rules.

```bash
make demo-up
make demo-verify
make demo-traffic
make demo-fault-errors
make demo-recover
make demo-down
```

Local endpoints:

- Checkout API: <http://localhost:8080/checkout>
- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3001> (`admin` / `sentinel-demo`)

The fault control and default Grafana credential exist only for this local lab.
