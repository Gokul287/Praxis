# On-call note — CDN cert rotation watch (filed 2026-04-24 22:10 UTC)

Heads up: this Friday's edge cert expiry window is **02:01 UTC** on
Saturday (i.e. tonight, ~4 hours from when this was written).

The ACME renewal job has been queueing for ~8 minutes today vs the
typical sub-minute latency. We bumped the management-account quota two
days ago which seems to have introduced the lag. The renewal will
probably complete on time but if it doesn't, the fastest recovery path
per ticket #4815 is `rollback_deploy service=cdn` to revert to the
previous edge build (which still has a valid chain through Sunday).

If you see TLS handshake failures at the edge **and** the renewal job
status looks "queued" rather than "running", don't wait — roll back.

(Worth pulling up runbook SRE-CDN-044 if this fires.)
