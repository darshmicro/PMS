# M22 (Attachments/Evidence) — Setup & Verification

## What's new in this module

```text
app/models/attachment.py           Attachment - EmployeeKPIID XOR RelatedEmployeeID,
                                     insert-only versioning via FileVersion
app/services/attachment_service.py  sanitize_filename, validate_extension, validate_size,
                                     ensure_exactly_one_target, virus_scan_hook,
                                     generate_stored_filename, next_file_version,
                                     storage_root, save_file, read_file
app/schemas/attachment.py          AttachmentOut
app/api/routes/attachments.py      5 endpoints: list, get, upload, download, export
sql/030_create_attachment_tables.sql   DDL: Attachments, with a CHECK constraint
                                     enforcing exactly one target FK
sql/031_seed_attachment_permissions.sql  New ATTACHMENT.VIEW / .EDIT codes
tests/test_attachment_service.py      14 unit tests
tests/test_attachment_routes_smoke.py  6 end-to-end ASGI tests (multipart upload)
```

## Design decisions

**No RBAC matrix row exists for this module - the same gap M18/M20/M21 already hit.** Section
5's matrix stops at "Audit Log." What the spec does give: Section 7's screen list has one
concrete anchor - "Self-Assessment form (per KPI, with evidence upload)" - an Employee-uploads-
own-evidence flow, matching `Employee_KPI.EvidenceRequired` (M11) and the ER diagram's own
`EMPLOYEE_KPI ||--o{ ATTACHMENTS : "evidence for"` relationship. Reading that alone would suggest
Employee-only uploads, the same as Self-Assessment (M12). But the DDL (Section 4.5) also carries
a second, nullable `RelatedEmployeeID` FK that **never appears in the ER diagram at all** - the
same kind of DDL-vs-narrative gap this codebase has resolved before (M14/M15/M18), here run the
other way: the DDL has a field the diagram omits, not the reverse. Declining to discard a field
the DDL literally specifies, this module treats `RelatedEmployeeID` as the general-purpose case -
an attachment scoped to an employee directly rather than to one specific KPI's evidence (a PIP
supporting document, say, which has no `EmployeeKPIID` to hang off of at all - Section 7 places
PIP management under HR). Since that second case needs HR/Manager-authored uploads, not
employee-authored evidence alone, `ATTACHMENT.EDIT` (upload) ends up broader than Self-
Assessment's "Employee only" rule: it's granted to the same full visibility set as
`ATTACHMENT.VIEW` (Employee/Manager/HOD/HR/Plant Head/MD/HR Administrator), with the actual
ownership check done per-request in the route handler (`_ensure_can_upload_for`) against whichever
target (KPI's owning employee, or `RelatedEmployeeID` directly) the caller named - because the
permission system alone can't know, at grant time, which specific record a given upload call is
about.

**Exactly one of `EmployeeKPIID`/`RelatedEmployeeID` per row, enforced at both layers.** Both
columns are nullable in the DDL with no `CHECK` given, so this module adds one -
`ensure_exactly_one_target()` in the service layer (the gate every request goes through) plus a
`CASE`-expression `CHECK` constraint in the DDL itself as a last-resort backstop against a direct
insert that bypasses the app - the same defense-in-depth pattern already used for Development
Plan's `CompletionStatus` and PIP's `Outcome` vocabularies.

**Versioning is insert-only, one row per version - never an overwrite.** `FileVersion` (the DDL's
own column) is the only versioning signal given; there's no history/superseded-by table or
`IsLatest` flag. This module never overwrites `StoredPath` in place, matching every other
insert-only/immutable pattern already in this codebase (`Audit_Log`, `Performance_Ratings`,
`PIP.Outcome` once closed): the next `FileVersion` is `max(existing FileVersion) + 1` for the same
logical slot - `(EmployeeKPIID, RelatedEmployeeID, FileName)` - so re-uploading a file under the
same original name against the same KPI/employee creates version 2, 3, ... as its own row, and
`GET /attachments?...&latest_only=true` collapses each slot down to its newest version for
callers that only want the current file. There is deliberately no `DELETE` or in-place update
endpoint - a superseding upload is the only way to "change" an attachment, so evidence already
referenced by an approved appraisal record is never silently removed or altered.

**Spec Section 9's file-upload control list, implemented one control per function.** "Extension
allow-list, size cap, stored outside web-root, filename sanitization, virus-scan hook point" maps
directly onto `validate_extension`/`validate_size`/`sanitize_filename`+`generate_stored_filename`/
`virus_scan_hook` in `attachment_service.py`. Two of these are flagged as interpretive additions,
the same way Development Plan's `CompletionStatus` and PIP's `Outcome` vocabularies were: the
allowed-extension set (`ALLOWED_EXTENSIONS`) is this module's own minimum list, since the spec
only asks for "an allow-list" in the abstract without enumerating one; and `virus_scan_hook()` is
a documented no-op - there's no anti-malware engine reachable from this environment to integrate
with, so every upload is routed through this function first and a future deployment can wire a
real scanner into it (raising on a positive match) without touching any caller. Physical bytes
are written under `settings.FILE_STORAGE_PATH` - declared in M1's `config.py` but unused until
now (see its own "used by later modules" comment) - using a random, collision-proof disk filename
that is never the caller-supplied one; `StoredPath` stores that generated name (a relative path,
not an absolute one, so the storage root can move without a data migration) while the original,
sanitized `FileName` is kept for display and download.

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| Extension must be in the allow-list | `validate_extension` | 400 |
| File must be non-empty and within the configured size cap | `validate_size` | 400 |
| Exactly one of employee_kpi_id / related_employee_id, never both, never neither | `ensure_exactly_one_target` | 400 |
| Caller must be broad-access, the record's manager/HOD, or its own subject | `_ensure_can_upload_for` | 403 |

## Setup

```sql
-- after 001-029 from M1-M21
:r sql/030_create_attachment_tables.sql
:r sql/031_seed_attachment_permissions.sql
```

Also set `FILE_STORAGE_PATH` in `.env`/environment to a real, access-controlled folder outside
the web root in production (spec Section 9); if left unset it defaults to `storage/attachments`
under the app's working directory, created on first use.

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**229 tests total (209 carried over from M1-M21 + 20 new)**, all passing with zero regressions:
unit tests for filename sanitization (including Windows-style `\` separators), the extension
allow-list, the size cap, the exactly-one-target rule, and the versioning helper
(`test_attachment_service.py`), plus **end-to-end ASGI tests** (`test_attachment_routes_smoke.py`,
which builds multipart/form-data bodies by hand since upload isn't a plain-JSON endpoint) covering
the full upload/download lifecycle including a second upload of the same filename producing
`FileVersion=2`, `latest_only` collapsing to just the newest version, an unsupported extension
being rejected, both-targets-at-once being rejected, the `RelatedEmployeeID` general-purpose case,
a Manager uploading/viewing within their own reports' scope but not for an unrelated employee, and
an Employee viewing but not uploading (no `ATTACHMENT.EDIT`).

Route registration was also verified via `app.openapi()`: **129 total paths** across 27 routers
(up from 125 paths / 26 routers in M21), **155 path+method combinations, zero collisions**.

## What M23+ will build on top of this

M23 (Notifications) is next. Its own DDL (`Notifications`, in the same Section 4.5 block as this
module's `Attachments`) is `EmployeeID`-scoped with no lock/appraisal-cycle tie either - the third
module in a row (after Development Plan and PIP) to sit outside the `Employee_Performance` chain.
Unlike this module, Section 5's screen list does give Notifications a concrete trigger list
("stage-based triggers"), so M23 should have more textual grounding for its authority/trigger
rules than M20-M22 needed to infer.
