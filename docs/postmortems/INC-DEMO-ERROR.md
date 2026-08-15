# Postmortem: INC-DEMO-ERROR

- **Status:** resolved
- **Severity:** SEV-2
- **Scope:** local reliability lab; no production users

## Summary

Controlled checkout failure exercised SentinelSRE detection, governance, recovery, and verification.

## Impact

Local synthetic checkout requests returned HTTP 503. No production users or cloud resources were involved.

## Detection

Incident Investigator Agent correlated a failed checkout request with the exported fault-mode metric.

## Timeline

| Time (UTC) | Event | Evidence |
| --- | --- | --- |
| 2026-08-15T00:04:14Z | detected | GET /checkout returned HTTP 503: {"status": "unavailable", "service": "checkout-api", "duration_ms": 10.64, "fault_mode": "errors"} |
| 2026-08-15T00:04:14Z | action proposed | ACT-C2E54DAF61EB: fault.recover |
| 2026-08-15T00:04:14Z | approved action started | approved by sai.demo |
| 2026-08-15T00:04:14Z | succeeded | fault mode is none; health endpoint returned HTTP 200 |

## Root cause

local demo fault injection is set to errors

## Contributing factors

- The basic health endpoint stayed green while the user-facing checkout path failed.
- The experiment intentionally activated a local-only application fault mode.

## Resolution and verification

checkout fault mode set to none

## What went well

- Runtime evidence identified the injected mode without granting the investigator mutation access.
- Unauthorized and unapproved paths were denied before execution.
- The approved adapter restored service and verified both fault state and health.

## Improvements

- Add an external synthetic availability probe so a green process-health endpoint cannot hide checkout failure.
- Export agent audit events to immutable cloud storage for production-grade retention.
- Replace demo identities and the local approval secret with enterprise identity and KMS-backed signing.

## Action items

| Owner | Action | Status |
| --- | --- | --- |
| commerce-sre | Add checkout-path synthetic probing to the SLO signal. | planned |
| platform-sre | Design immutable audit export for AWS and Azure. | planned |
| security-platform | Integrate workforce identity with approval verification. | planned |

## Evidence integrity

- Request: `ACT-C2E54DAF61EB`
- Request SHA-256: `c2e54daf61eb60084ebbed43b34c55b065759d08259cd1e51ad418715fcf95a4`
- Audit event SHA-256: `cfcbed6871c1c15c2a4f1223825298172948afbb32dd6c1a4ffeeb1bf64babcf`
- Investigator: `IncidentInvestigatorAgent`
- Approver: `sai.demo`

This is a blameless review of system behavior and control effectiveness.
