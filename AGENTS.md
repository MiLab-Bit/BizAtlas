# BizAtlas — Codex/Agent Review Rules

Actual architecture: FastAPI business-risk scoring + React client, RBAC/HMAC, uploaded documents and deterministic scoring rules. LLM extraction/wording must never be allowed to invent financial numbers, alter approved rules or sign off decisions.

Inspect changed API, rule evaluation, upload paths and existing tests before suggesting fixes. Explicitly identify score rule owner, data provenance, access control, trust boundaries and financial-analysis uncertainty. Test unauthorized tenant access, auth-disabled development fallback leaking into production, unsafe PDF/XLSX parsing, API keys, report export, pilot rule promotion and model hallucination gates. Preserve existing CLAUDE.md and RELEASE.md.

Review comments must cite exact SHA/file/line, reproducible negative case, consequence and minimal change, not a generic refactor. Missing source/test evidence is NOT VERIFIED. No automatic merges, production deployments or private data use. ChatGPT implements, Codex is second-agent reviewer, owner decides merge and acceptance. See SECURITY.md.
