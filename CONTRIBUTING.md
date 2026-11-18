# Contributing to BizAtlas

BizAtlas is a financial risk analysis application. Contributions should preserve the distinction between **source data, deterministic calculations, rules, and model-generated explanations**.

## Proposing changes

- Check existing issues and pull requests before opening a new one.
- Explain the user problem, affected workflow, and expected output.
- Keep pull requests small and include any relevant documentation changes.
- Do not submit real customer financial records, credentials, private company reports, or personal information as fixtures.

## Verification checklist

In each pull request, report:
1. The exact commands you ran and their results; label unrun checks explicitly.
2. Sample inputs and expected outputs using synthetic or appropriately licensed public data.
3. The source and as-of date of any external data used in the change.
4. Effects on risk ratings, rules, scoring weights, and report exports.
5. Whether a failure mode can lead to unsupported or misleading financial conclusions.

For scoring or rules changes, include a before/after example and a rationale for thresholds. For retrieval or AI explanations, distinguish retrieved evidence from inference, and test missing, conflicting, and stale sources.

## Responsible reporting

Do not post exploitable security details in public issues. Check GitHub's private vulnerability reporting settings or contact the maintainers privately. Avoid including API keys, tokens, customer files, or private logs in bug reports.

## Scope and limitations

A passing unit test is not proof of real-world financial accuracy. Avoid claims of regulatory certification, creditworthiness guarantees, or production readiness unless independently substantiated. Clearly document assumptions and known limitations.

## Licensing

Before reusing third-party datasets, code, or documents, confirm their redistribution and attribution terms. Contributors should check the repository's current license status before assuming any grant of reuse rights.
