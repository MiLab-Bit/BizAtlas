# BizAtlas — Security Review Policy

Sensitive surfaces: authentication-disabled or missing-secret development mode that grants anonymous admin, API-key versus JWT token principal handling, organization data access, financial report uploads, PDF/Excel parsers, LLM prompt injection, scoring rules and risk assertions, report serialization, persistent document storage and third-party calls.

Never process real borrower/client data or live credentials during routine review. Model output cannot become an authoritative score, fabricated input value or approved rule without deterministic checks and authorized promotion. A real finding needs SHA, path, trusted/untrusted boundary, synthetic reproduction, impact and smallest safe fix. Do not leak exploit payloads or secrets through public PRs; use repository owner's private channel or GitHub private advisories if actually enabled. No certification implied.
