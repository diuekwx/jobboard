# Deployment roadmap

Last updated: 2026-09-07

## Agreed direction

- Deploy server-side Gmail processing and encrypted database storage on Hostinger KVM 2 (2 vCPU, 8 GB RAM).
- Prefer local inference with no per-token cost. Benchmark a quantized 4B model before choosing the production model.
- Keep the modular monolith; separate email fetching, classification, persistence, and job execution.
- Encrypt sensitive fields and integration tokens before database writes. Server-side encryption protects stored data, but the server operator can still access plaintext during processing.
- Minimize retained email content. Never put secrets or real email content in project documentation or test fixtures.
- Defer browser processing and user-held encryption until after the beta. Preserve clear interfaces for that future work without implementing two architectures now.

## How to use this roadmap

Work through milestones in order. Each milestone can be a separate implementation task. Read the current code before acting: findings from the initial review are starting points, not a substitute for verification.

Check items only after implementation and relevant verification. Record decisions, verification results, and remaining limitations under the milestone. Do not claim benchmarks or checks passed unless they were actually run.

Google OAuth production requirements should be investigated early, alongside the engineering work, because external approval may affect the release schedule.

## 1. Working development baseline

- [ ] Repair/document Python and Node setup.
- [ ] Run backend tests, TypeScript checks, lint, and frontend build; resolve failures.
- [ ] Track required source files and remove unused starter files where appropriate.
- [ ] Pin dependencies and provide a safe `.env.example` with placeholders only.
- [ ] Write fresh-checkout setup instructions and an architecture overview.

**Done when:** a fresh checkout can run and verify the project using documented commands.

## 2. Database foundation

- [x] Introduce versioned Alembic migrations for fresh and existing databases.
- [x] Correct timestamp defaults and timezone handling.
- [x] Standardize application statuses and validate API inputs.
- [x] Add appropriate ownership indexes and uniqueness constraints.
- [x] Identify applications by ID when editing instead of company/role.

**Done when:** a fresh database and an existing database can safely reach the same schema.

**2026-09-05 implementation:** Added frozen baseline and foundation revisions, strict
legacy-schema adoption, preflight conflict checks, UTC timestamp handling, validated
statuses (`sent` migrates to `applied`), token/event uniqueness, child lookup index,
and ownership-scoped UUID edits. See [migration instructions](backend/MIGRATIONS.md).
Disposable SQLite tests verify fresh/adopted schema convergence and data retention.
PostgreSQL execution and backup restoration still need verification before calling
the milestone production-ready. No configured database was modified.

## 3. Encrypted storage and minimal retention

- [x] Define the threat model and inventory sensitive fields and searchable identifiers.
- [x] Encrypt application details, notes, event details, and integration tokens using established authenticated encryption.
- [x] Keep encryption keys outside the database and document backup, recovery, and rotation.
- [x] Plan and verify migration of existing sensitive plaintext records.
- [x] Remove unnecessary stored email bodies and sensitive content from logs, errors, and processed-message details.
- [x] Document necessary unencrypted metadata and the limits of server-side encryption.

**Done when:** a database export does not reveal sensitive application details or usable Gmail tokens, and authorized recovery is verified.

**2026-09-06 implementation:** Added versioned AES-256-GCM application-level
encryption, HKDF-separated keyed lookups for Gmail identifiers, forward-only
plaintext migration, minimal email retention, and sensitive-log regression
coverage. The configured PostgreSQL database was migrated and audited with zero
unencrypted protected values or missing required lookups. Automated tests verify
raw SQL and SQLite dump confidentiality, tamper detection, wrong-key failure,
and recovery of a copied encrypted database using the matching key. A production
PostgreSQL backup/restore rehearsal and external secret-manager configuration
remain deployment tasks for milestone 10.

## 4. Gmail sync correctness

- [x] Handle pagination without losing older messages at scan limits.
- [x] Make moving the start date backward perform a real backfill.
- [x] Preserve failed and deferred messages for retry.
- [x] Advance checkpoints only after the relevant work completes.
- [x] Handle out-of-order messages, duplicate runs, and interrupted scans.
- [x] Add regression tests for large backlogs, fetch failures, backfills, interruptions, and deduplication.

**Done when:** interruptions, large inboxes, and retries do not silently lose or duplicate applications.

**2026-09-06 implementation:** Gmail listing now walks past already-processed
pages, applies a per-run limit to new work instead of the newest result slice,
and advances the checkpoint captured at scan start only after pagination and all
selected work complete. Earlier start dates reset the checkpoint for backfill;
failed and deferred messages remain unprocessed for retry; and messages are
applied by received time. Automated tests cover a 205-message multi-page
backlog, fetch failure, deferral, backfill, newest-first results, interruption,
and duplicate runs. The live Gmail API has not been exercised by these tests.

## 5. LLM fallback reliability

- [x] Separate classification from Gmail fetching and database updates.
- [x] Define a shared, validated classification-result format that a future browser processor could also produce.
- [x] Validate allowed categories, field lengths, message identifiers, and completeness of batch results.
- [x] Add explicit timeouts and account for attempted requests/emails, retries, tokens, and elapsed time.
- [x] Keep failed classifications pending; distinguish intentional rules-only operation from a model outage.
- [x] Improve excerpts by removing quoted history and boilerplate while preserving relevant evidence.
- [x] Supply received timestamps for relative dates and treat email instructions as untrusted data.
- [x] Require review for ambiguous classifications and application matches rather than trusting model confidence alone.

**Done when:** malformed output and provider outages cannot silently finalize incorrect results.

**2026-09-06 implementation:** Added a strict portable classification contract,
complete message-ID-aligned batch validation, sanitized excerpts, received-time
anchors, prompt-injection boundaries, explicit request timeouts, and sync-level
request/retry/token/latency accounting. A zero LLM budget is reported as
intentional rules-only operation; model outages, invalid or incomplete output,
and budget overflow remain pending without ledger writes or checkpoint advance.
Model-only, conflicting, low-confidence, and ambiguous application matches are
marked for review. Automated tests cover contract limits, incomplete batches,
outages, rules-only mode, retries, timeouts, usage accounting, excerpt cleanup,
untrusted content, and ambiguous matching. Live provider behavior has not been
exercised.

## 6. Background scanning and bounded concurrency

- [x] Move scans into durable jobs and initiate scans with POST.
- [x] Allow one active sync per user and recover jobs after worker restarts.
- [x] Fetch Gmail messages with a small concurrency limit, respecting API quotas.
- [x] Start with one global local-model inference slot and fair scheduling across users.
- [x] Keep database sessions and Google client transports out of unsafe shared concurrent use.
- [x] Apply database updates in a controlled order with deduplication safeguards.
- [x] Show job progress and partial results without discarding existing applications.

**Done when:** scanning survives closing the page and restarting the worker without losing completed work.

**2026-09-07 implementation:** Added database-backed scan jobs, atomic per-user
active slots, worker leases and expired-job recovery, POST initiation and
progress endpoints. The single worker processes capped slices in oldest-served
order so another user's queued scan gets a turn before a large mailbox resumes.
Gmail fetches use four isolated client transports by default; model inference
has one guarded slot; database effects stay timestamp-ordered and commit with
job progress in chunks. The dashboard polls progress and refreshes partial
results without replacing the existing board. Automated SQLite/fake-Gmail tests
cover active-job uniqueness, recovery, durable progress, bounded continuation,
fair yielding, and the existing interruption/deduplication behavior. The worker
and Gmail concurrency have not been exercised against the live Gmail API, and
the supported initial deployment is exactly one scan worker.

## 7. Authentication and account controls

- [ ] Require production secrets and HTTPS cookie settings; remove insecure fallbacks and sensitive OAuth logging.
- [ ] Clean up OAuth state handling and duplicate authentication paths.
- [ ] Add CSRF protection appropriate to cookie authentication and rate limits.
- [ ] Implement logout and Gmail disconnect/reconnect, including credential revocation/removal as appropriate.
- [ ] Implement account deletion and define backup-retention behavior.
- [x] Simplify the initial release to Google sign-in only.
- [ ] Test cross-user data isolation and authentication failure paths.

**Done when:** the account lifecycle and cross-user isolation are verified.

## 8. Essential product workflows

- [ ] Support adding, editing, and archiving applications and notes.
- [ ] Add a review queue with correction, merge, and undo actions.
- [ ] Support offers, accepted, and withdrawn outcomes consistently across processing and UI.
- [ ] Show source-backed application history.
- [ ] Handle expired sessions and scan failures without clearing the board.
- [ ] Add data export and clear onboarding.

**Done when:** users can correct automation mistakes and manage their search without database intervention.

## 9. Local inference evaluation and tuning

- [ ] Build a sanitized, labeled evaluation dataset with difficult and negative examples.
- [ ] Compare rules-only classification with rules plus a quantized 4B model.
- [ ] Measure per-class accuracy, company/role extraction, application matching, and date accuracy.
- [ ] Measure model usage, batch latency, full-scan duration, peak RAM, and API responsiveness on KVM 2.
- [ ] Benchmark batch sizes and verify thinking is disabled for the chosen runtime/model where supported.
- [ ] Choose the production model and resource limits from measured results.

**Done when:** expected accuracy and throughput are documented with reproducible measurements.

## 10. Private staging deployment

- [ ] Package frontend, API, database, worker, queue, and Ollama reproducibly.
- [ ] Configure HTTPS, environment-specific URLs/origins, migrations, and restart policies.
- [ ] Keep PostgreSQL, the queue, and Ollama off the public internet.
- [ ] Add health checks, resource limits, and monitoring that excludes sensitive content.
- [ ] Configure encrypted backups and appropriate access controls.
- [ ] Test data/key restoration and deployment rollback.
- [ ] Verify live OAuth and PostgreSQL behavior in staging.

**Done when:** restarts and failed deployments do not lose data, keys, or queued work.

## 11. Friends beta and privacy readiness

- [ ] Investigate applicable Google OAuth verification and Gmail data requirements early; complete prerequisites before the intended release.
- [ ] Publish a plain-language privacy notice covering server processing, encryption limits, retention, deletion, and backups.
- [ ] Explain that server-side encryption does not prevent the server operator from accessing data.
- [ ] Start with a few users and collect feedback without collecting their email content.
- [ ] Monitor failures, queue delays, resource use, and correction rates.
- [ ] Verify onboarding, scanning, correction, disconnect, export, and deletion end to end.

**Done when:** friends can use the full lifecycle reliably and understand how their data is handled.

## 12. Portfolio polish and follow-up features

- [ ] Create a public demo using synthetic emails and applications, without requiring mailbox access.
- [ ] Add screenshots, an architecture diagram, and measured evaluation results to the README.
- [ ] Automate backend tests and frontend checks in CI (move earlier if useful).
- [ ] Write resume bullets using actual measured results, without invented accuracy or usage claims.
- [ ] Evaluate calendar export, deadline reminders, and response-time analytics after core feedback.

**Done when:** someone can understand and try the project, and its engineering claims have supporting evidence.

## Deferred: stronger privacy mode

This is a future architectural feature, not a simple classification toggle.

- [ ] Prototype browser rules and optional on-device inference on representative devices.
- [ ] Move Gmail authorization/access to the client so the server retains no usable mailbox credential.
- [ ] Encrypt records on the client with user-held keys before upload.
- [ ] Design recovery, encrypted backup, and later multi-device synchronization.
- [ ] Define migration from hosted mode, including revoking server Gmail access and explaining old-backup expiry.
- [ ] Explain browser execution limits and the trust placed in delivered application code.

## Decision and verification log

- **2026-09-05:** Agreed to prioritize VPS processing with encrypted storage; browser processing is deferred. This roadmap is a plan, not a record of completed implementation.
- **Initial review baseline:** TypeScript compilation and ESLint passed in the review session. Vite bundling was blocked by filesystem access restrictions. Backend tests could not run because the existing virtual environment referenced a missing Python installation and the default Python shim was unconfigured. Re-run all checks in milestone 1.
