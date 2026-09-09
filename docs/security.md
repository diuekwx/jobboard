# Security and privacy design

## Threat model

### Sensitive assets

The application stores or processes:

- Gmail access and refresh tokens.
- Company names and job titles.
- Application notes and status history.
- Recruiter email addresses and email subjects.
- Interview and assessment information.
- Gmail message and thread identifiers.
- Email bodies temporarily received during Gmail synchronization.
- User email addresses and Google OAuth tokens.
- Encryption keys and application-signing secrets.

### Threats this design addresses

Application-level encryption is intended to protect sensitive data when:

1. A database file or database export is stolen.
2. A database backup or snapshot is exposed.
3. Someone obtains read-only SQL access without access to the application server.
4. Database files are accidentally copied or shared.
5. Old database storage is accessed after it is discarded.

Sensitive data must also be excluded from application logs, exception messages,
test fixtures, analytics, and monitoring output.

### Threats this design does not address

This design does not protect data when:

1. An attacker controls the running application server.
2. An attacker obtains both the database and its encryption keys.
3. The server operator deliberately reads data while the application is processing it.
4. A user's browser, Google account, or device is compromised.
5. An authenticated user is tricked into exposing their own information.
6. Plaintext is sent to an external model or service during classification.

The server must be able to decrypt data to provide the application, so this is
server-side encryption rather than zero-knowledge or end-to-end encryption.

### Security objectives

- A database export must not reveal Gmail access or refresh tokens.
- A database export must not reveal company names, job titles, notes, recruiter
  correspondence, or event titles.
- Modifying encrypted data must cause decryption to fail.
- Encryption keys must not be stored in the database or source repository.
- Losing the encryption key must not silently corrupt or replace encrypted data.
- Existing plaintext data must not be deleted until its encrypted replacement has
  been verified.
- New logs and errors must not include email content, credentials, or sensitive
  application details.

### Accepted metadata leakage

The initial design may leave the following operational metadata unencrypted:

- Internal UUIDs and relationships.
- Application status and source.
- Application, event, and processing timestamps.
- Whether an application needs review.
- Integration provider name and token expiration time.
- Non-sensitive machine-readable outcome and error codes.

A database reader may therefore learn when activity occurred and how many
applications or events exist, but not the companies, roles, notes, message
contents, or usable Gmail credentials.

### Key assumptions

- Production encryption keys are generated randomly.
- Production keys are stored outside the database and Git repository.
- Database backups and encryption-key backups are stored separately.
- Access to production secrets is restricted to the application service and
  authorized operators.
- HTTPS and normal authorization controls are still required; encryption at rest
  is an additional layer, not a replacement for them.


  ## Data inventory

| Table | Field | Sensitivity | Treatment | Reason |
|---|---|---:|---|---|
| users | email | High | Initially plaintext; restrict access and document | Used for login and exact lookup |
| applications | company_name | High | Encrypt; add blind index if exact lookup is needed | Reveals where the user applied |
| applications | position | High | Encrypt; add blind index if exact lookup is needed | Reveals job-search details |
| applications | notes | High | Encrypt | May contain personal or recruiter information |
| applications | application_date | Medium | Plaintext metadata initially | Needed for sorting and matching |
| applications | status | Medium | Plaintext metadata initially | Needed for board filtering and workflow |
| applications | source | Low | Plaintext | Operational metadata |
| applications | needs_review | Low | Plaintext | Operational flag |
| applications | gmail_message_id | Medium | Prefer keyed blind index; retain encrypted value if permalink is required | Used for deduplication and Gmail links |
| applications | gmail_thread_id | Medium | Prefer keyed blind index plus encrypted value | Used for thread matching |
| integration_tokens | access_token | Critical | Encrypt | Grants temporary Gmail access |
| integration_tokens | refresh_token | Critical | Encrypt | Can obtain new Gmail access tokens |
| integration_tokens | external_user_id | Medium | Encrypt unless exact lookup is required | Identifies an external account |
| integration_tokens | provider | Low | Plaintext | Needed to select the integration |
| integration_tokens | expires_at | Low | Plaintext | Needed to know when refresh is required |
| recruiter_responses | sender_email | High | Encrypt | Personally identifying correspondence |
| recruiter_responses | subject | High | Encrypt or stop retaining | May reveal company, role, or decision |
| recruiter_responses | body | Critical | Stop retaining after classification | Full email content is unnecessary after extraction |
| recruiter_responses | received_at | Medium | Plaintext metadata initially | Needed for ordering/history |
| events | title | High | Encrypt | Usually contains a company or role |
| events | event_type | Medium | Plaintext metadata initially | Needed for UI behavior |
| events | start_time | Medium | Plaintext metadata initially | Needed for ordering and reminders |
| events | end_time | Medium | Plaintext metadata initially | Needed for reminders |
| events | source_message_id | Medium | Keyed blind index or encrypted value | Used for deduplication |
| processed_messages | gmail_message_id | Medium | Keyed blind index | Used for deduplication |
| processed_messages | gmail_thread_id | Medium | Keyed blind index if retained | Used for matching |
| processed_messages | outcome | Low | Plaintext machine-readable code | Operational state |
| processed_messages | detail | Low | Plaintext machine-readable reason code | Email subjects were removed and historical details cleared |

## Implemented storage design

Sensitive fields use AES-256-GCM authenticated encryption in the application
before SQL writes. Each value has a fresh random 96-bit nonce and a versioned
envelope containing its key ID. Associated data binds ciphertext to its table
and column, so moving it to a different protected field fails authentication.

Gmail message and thread IDs remain readable to application code but are
ciphertext in the database. Equality and uniqueness use HMAC-SHA-256 blind
indexes derived from the master key with a separate HKDF purpose. Company and
role matching decrypts only the current user's applications in memory; no
guessable company-name lookup hash is stored.

Full recruiter email bodies are used temporarily during classification and are
not retained. Processed-message details contain only classifier method codes
such as `rules`, `llm`, or `rules+llm`.

The following remain plaintext metadata: user email,
application status/date/source/review flag, event type/timestamps, provider,
token expiration, processing outcome/timestamps, row IDs, and relationships.

## Key storage and recovery

- Development keys may live in the ignored local `.env` file.
- Production keys must be injected from a protected secret file, container
  secret, or secret manager and must not be baked into an image.
- Production and development use different randomly generated keys.
- Keep an encrypted recovery copy separately from database backups.
- A usable backup requires both the database and the matching encryption key.
- Test recovery on a disposable restored database before relying on a backup.
- Never print keys, plaintext, tokens, or complete ciphertext in logs.

## Key rotation

Encrypted envelopes record a key ID. To rotate a key, deploy code that can read
both the old and new key IDs, use the new key for all writes, re-encrypt rows in
resumable batches, rebuild blind indexes, verify every row, and only then retire
the old key. Retain an old key only as long as backups encrypted with it must be
recoverable. Rotate immediately after suspected disclosure.

The current runtime accepts one active key, so rotation must be performed as a
planned migration rather than by replacing the environment value in place.
Changing the key without re-encrypting data makes existing records unreadable.
