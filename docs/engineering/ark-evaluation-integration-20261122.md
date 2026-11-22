# Ark evaluation integration gate — 2026-11-22

Source packages: task 37699, frore 90667; vugh 90666; xyst 90668. This is an integration worklist, NOT evidence of code integration.

## Candidate adoption
1. Inspect frore's immutable observation ledger, current-value projections, quarantine, replay/rebuild checks and tests. Prefer porting cohesive components into the existing data pipeline, not replacing the application.
2. Evaluate vugh's CSV/TXT/event/graph adapters independently, preserving original bytes and provenance.
3. Evaluate xyst's 51-rule catalog as configuration, not as unquestioned business authority.

## Mandatory safety gates
- When source registration and legal/compliance documentation disagree (especially qichacha), fail closed: quarantine until explicit authorized review; never silently accept the registry's precedence.
- Keep processing integrity and business data quality separate. Neither passing tests nor complete ingestion implies verified facts.
- Preserve immutable raw observations, per-source attribution, conflict records, deterministic replays, rollback and rebuild equivalence.
- Confirm API/downstream compatibility, no-loss migration, multi-run idempotence and performance before merging.
- Re-run repository baseline and new regression tests. Record commands, environment, outputs, and remaining limitations.

Status: review pending; no candidate code has been cherry-picked or merged.
