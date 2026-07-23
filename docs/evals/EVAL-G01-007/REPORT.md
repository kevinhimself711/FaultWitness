# EVAL-G01-007 Report

## Result

Result: **PASS** on final candidate `cea2e63948d86bac3a3ae5d3afa68b477f20e3c2`.

Candidate `ae0a3be535d60db2aa15a6355c0f321e84803a2e` deployed migration `003_i0013` and the private Trace Service. The candidate-bound checkpoint passed nine primary checks: encrypted owner-isolated schema, private ClusterIP deployment, live sanitized LangSmith delivery, OTLP trace/metric/log delivery, MinIO/DVC archival, idempotent duplicate ingest, pre-persistence canary rejection, zero pending delivery, and public/private evidence separation.

The sanitized LangSmith run `8a2a2a56-302c-51ce-ae75-2fca80932b97` returned HTTP 200 on independent readback and carried the exact candidate metadata and payload digest. Platform bundle digest: `0d54d64534dda49327731cde0d0453dc9fcf9b8875096bc065b18a3b7cbc671a`; Trace Service bundle digest: `f2912270c1e0e6f8c30b1e6f3c4c6b9bc30a81c50da4e05f827b19b7be688af7`; migration digest: `e127fe8110bf1c317e10569e351792e6f0e1306d0a6e2650ecf499371bd2d21a`.

Direct LangSmith TLS handshakes from the private server timed out while the same endpoint and credential succeeded from the pinned operator host. The current deployment therefore keeps LangSmith delivery pending on-server, claims only sanitized ciphertext through a host-key-pinned SSH tunnel, exports locally, and ACKs only after LangSmith success. This is an implemented evidence path, not a waiver or a claim that server egress works.

## Required evidence

- Complete backend outage and uncertain-ACK replay matrix.
- All-surface secret/PII/private-reasoning scan and cross-store correlation queries.
- Independent wall-time reconciliation and final LangSmith usage count.

## Open evidence at implementation checkpoint

- Backend outage/uncertain-ACK replay with zero duplicate or lost span.
- Cross-store correlation, independent wall-time reconciliation and final usage count.
- Full persistence/egress canary scan and rejected-payload absence proof across every surface.

## I-0015 replay checkpoint

Candidate `9b853261c6071e33c7979da8478879952a790937` passed a live
uncertain-ACK replay through LangSmith: the same sanitized Trace reference,
payload digest, and remote trace identity were exported twice around a simulated
ACK loss and the durable queue drained to zero. Final-candidate all-surface
canary/correlation and independent wall-time/usage reconciliation remain open.
