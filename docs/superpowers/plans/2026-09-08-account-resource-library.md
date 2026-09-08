# Account Resource Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver the approved Syncthing account library, placeholders, migration/export/import, version conflicts, and desktop management together.

**Architecture:** Immutable content objects and parent-linked revisions in the shared folder; local settings and materialized workspaces adapt the existing episode-oriented engine. Transfers are resumable local transactions. Platform observations and resource versions are reconciled without treating Syncthing as a distributed lock.

**Tech Stack:** Python 3.9+, pathlib/hashlib/json, existing pytest; Electron, Vue 3, Pinia, Vitest.

**Workspace:** `/Users/zeen/.config/superpowers/worktrees/sticker-maker/account-sharing`, baseline `b7a0ab8` preserves the user's current source. Original checkout must retain pre-existing changes.

## Contracts shared by implementation tasks

Python core in `sticker_engine/sticker_engine/library/catalog.py`:

```python
class ResourceLibrary:
    def __init__(self, root, create=False): ...
    # root: Path; library_id: str
    def put_file(self, path): ...  # {sha256: str, size: int}
    def write_revision(self, account_id, work_id, metadata, files,
                       parents=None, deleted=False): ... # revision dict
    def read_work(self, account_id, work_id): ...
    def list_works(self, account_id=None): ...
    def materialize(self, account_id, work_id, target, revision_id=None): ...
    def merge_from(self, source): ... # validate and copy immutable content
    def resolve(self, account_id, work_id, revision_id): ...
```

`files` maps portable logical relative paths to `{sha256, size}`. A revision has `revision_id`, `parents`, `account_id`, `work_id`, `metadata`, `files`, `deleted`. `read_work` returns `{account_id, work_id, state, revision, heads, missing}`; states `available`, `placeholder`, `pending`, `conflict`, `deleted`. `heads` are revision dicts. Metadata contains existing EpisodeMeta fields plus `kind` (`episode` default, `settings` for shared preferences), `account_label`, `legacy_name`. Missing/corrupt parents block activation. Metadata is caller-sanitized, paths validated by core.

Transfer layer in `library/transfer.py`:

```python
class TransferManager:
    def __init__(self, state_dir): ...
    def preview(self, sources, target, mode='backup', cleanup=False): ...
    # sources=[{path, account_id, work_id, metadata, extra_files?}]
    # extra_files={logical_relative_path: absolute_source_file}
    # returns JSON plan including plan_id, mode, target, entries, missing, bytes
    def execute(self, plan_id, activate=None, should_stop=None, progress=None): ...
    # activate(target) performs persisted switch; only clean after it succeeds.
    def tasks(self): ...
```

Only `migration` allows cleanup. Plans live in local state, execute revalidates every source, target and hash; only files under explicit source directories can be cleaned. Repeated execution resumes from actual verified files, never deletes new/changed source. Imported immutable libraries use core `merge_from`, legacy import uses preview/execute through runtime.

Desktop IPC commands (normal `{status:'ok',data}` response):

```text
library_status {} -> {connected, root, library_id, account_id, account_label, accounts, counts, tasks, conflicts}
library_bind_account {account, confirm_legacy:true} -> status
library_preview {target, mode:'backup'|'migration', cleanup} -> plan
library_execute {plan_id} -> {state, target, copied, cleaned, missing, errors}
library_connect {path} -> status
library_import {path} -> {imported, ...status}
library_refresh {} -> status
library_resolve {work_id, revision_id, action:'choose'|'draft'} -> status
library_delete {work_id, action:'hide'|'delete'|'restore'} -> status
library_handoff {} -> {message}
library_capture {episode_dir} -> {work_id, revision_id}
```

Counts: `{available, placeholder, pending, conflict, deleted}`. Accounts: `[{account_id, account_label}]`. Conflicts: `[{work_id, album_name, heads:[{revision_id, metadata, ...}]}]`. Existing list/get episode responses gain `work_id, account_id, resource_state, can_edit, can_publish, can_shelf`; retain `path` for legacy callers. Pending/conflict are never uploadable. Work detail carries these fields at top level.

## Task 1 — Immutable catalog and portable materialization

Owner: Luna core. Files: `library/__init__.py`, `library/catalog.py`, `library/resources.py`, `tests/library/test_catalog.py`.

- [x] Write and observe failing tests for roundtrip, repeated import, account partition, object-first/manifest-first order, missing parent, two diverging edits, choose-merge, tombstone/edit conflict, hash corruption, unsafe paths.
- [x] Implement contract above using atomic temp-file replacement, SHA-256 content keys and UUID revision IDs. Explicit parent sets retain branches; default parents are current complete heads. No mtime winner and no shared mutable index.
- [x] Materialize only validated complete versions into a dedicated target, retain portable names, reject links/escape/reserved names/case collisions. Refuse unknown library format, malformed manifests, loops and conflict files.
- [x] Run `/tmp/sticker-review-20260907-venv/bin/python -m pytest tests/library/test_catalog.py -q` from `sticker_engine`.

Behavior test example:

```python
def test_out_of_order_objects_stay_pending(tmp_path):
    a = ResourceLibrary(tmp_path / 'a', create=True)
    b = ResourceLibrary(tmp_path / 'b', create=True)
    raw = tmp_path / 'raw'; raw.write_bytes(b'image')
    rev = a.write_revision('account', 'work', {}, {'原图/raw.png': a.put_file(raw)})
    dst = b.root / 'accounts/account/works/work/revisions' / (rev['revision_id'] + '.json')
    dst.parent.mkdir(parents=True)
    dst.write_text(json.dumps(rev), encoding='utf-8')
    assert b.read_work('account', 'work')['state'] == 'pending'
```

## Task 2 — Transactional export and migration

Owner: Luna transfer, after core API is established. Files: `library/transfer.py`, `tests/library/test_transfer.py`.

- [x] Write and observe failing tests for missing sources, source/target ancestry, successful backup, migration activation failure, cleanup opt-in, cancellation/resume, changed source, external dependencies, cleanup failure, persisted restart.
- [x] Persist preview before execution; reject credential/browser/API files from capture. Copy all source episode files and explicit referenced extras; include a missing manifest instead of claiming completion.
- [x] Copy and verify into ResourceLibrary, call activate only for complete migration, verify destination again before deleting each unchanged managed source. Preserve external source files and Syncthing management files.
- [x] Return accurate partial result; resume by plan ID without mutable frontend file paths.
- [x] Run `/tmp/sticker-review-20260907-venv/bin/python -m pytest tests/library/test_transfer.py -q`.

## Task 3 — Runtime, account binding and existing engine integration

Owner: root. Files: `library/runtime.py`, `library/commands.py`, `cli.py`, `config/paths.py`, `config/series.py`, `publish/platform_data.py`, `publish/status.py`, new runtime/integration tests.

- [x] Write failing tests for account placeholders, repeat sync, connection/restart, matching resource hydration, hidden vs shared delete, account mismatch, metadata capture, partial versions and command dispatch.
- [x] Keep local device config separate from shared resources; route active output to a per-device workspace while snapshots enter the connected library. Store local fallback library for placeholders before sharing.
- [x] Bind accounts explicitly, adapt old work IDs and custom/series/reference/prompt dependencies. Share settings as versioned settings entities; restore references to materialized local resources.
- [x] Introduce commands in a separate module and wrap relevant CLI operations for local locking, refresh-before-use, materialize-before-edit, capture-after-success and account checks. Generation failures still preserve a draft snapshot.
- [x] Extend platform API and DOM fallback to construct unmatched placeholders with stable IDs; preserve account separation and reason history. Upstream incomplete reads do not delete entries.
- [x] Preserve exact current platform targeting and true success conditions. Record platform operation intent/result, block unsafe auto-retry and surface uncertain outcomes.
- [x] Run targeted library/platform/CLI suites, then backend suite including agent tests when dependencies permit.

## Task 4 — Desktop flows

Owner: Luna UI; only renderer and new UI tests. Files: new `ResourceLibraryPanel.vue`, `SettingsPanel.vue`, `EpisodesPanel.vue`, `EpisodeDetailPanel.vue`, new component tests. Avoid store changes unless agreed.

- [x] Write failing component tests for preview-before-execute, cleanup default false, canceled folder chooser, status errors, placeholder open, upload gating, conflict selection and shared delete confirmation.
- [x] Add a settings resource-library tab with account binding, library location, export purpose/target/cleanup, preview and execute, copy-import vs connect, refresh, pending tasks/resume, version conflict choices and handoff.
- [x] Show current resource state separately from platform status. Enable details for placeholders; hide/disable content-edit actions unless can_edit; upload requires can_publish. Expose capture/manual edits and distinct local hide/shared delete/restore.
- [x] Poll only while component is mounted, never claim peer synchronization. Keep skin consistent with existing cream/forest design, accessible controls and narrow-window layout.
- [x] Run `npm test` and `npm run build` with Node 24 PATH.

## Task 5 — Review, complete integration and delivery

- [x] Perform spec review then independent quality review; fix new gaps and retest affected behavior.
- [x] Run complete backend and frontend suites once integration is stable. Record existing baseline failures separately; fix task-caused failures.
- [x] Test actual CLI migration, restart and second-device connection in temporary Chinese-path fixtures using seven independent JSON-lines processes. Catalog/runtime tests separately cover incomplete versions, conflicts and deletion restoration.
- [x] Render desktop UI against seeded safe fixtures and inspect screenshots; do not submit real platform works during tests.
- [x] Update `doc/README.md`, add `doc/reference/resource-library.md`, mark design/plan status accurately. Record Windows/Syncthing physical-device checks as unverified if no environment is available.
- [x] Return only feature diff from baseline to original workspace after checking unchanged baseline content. Commit feature work in isolated branch; do not commit or overwrite user's unrelated original modifications.

## Delivery verification (2026-09-08)

- Desktop: 65 tests across 12 files passed; Vite production build passed.
- Backend: 462 tests passed, including final cleanup and task-resume regressions (10 existing Pillow deprecation warnings).
- Real JSON-lines smoke: migrate with original cleanup, restart, connect second local device, verify stable identity and readable original. No real user assets were migrated during development.
- Desktop and 390px screenshots inspected using safe mock data.
- Physical Windows/macOS Syncthing transfer and live platform submission remain unverified. Syncthing installation/pairing is external to the app.
- Existing generation test assertions were corrected to reflect the already implemented four reserved portrait slots; generation behavior was not changed for those fixes.
- Shared library resides in the chosen root; per-device mutable workspace resides in its adjacent `.sticker-maker-workspaces` directory. Legacy auto-capture stops after connection.
- Full-library export includes settings/history. Cleanup candidates are registered files only, with verified target copies and confined deletion. Unknown user files are retained.

## Real-library migration hardening (2026-09-08, evening)

User-driven live migration of a real Windows library (12,370 files / 2.0 GB, 308 works) to `E:\共享\星星布丁\微信表情包\周三涵做表情`, with cleanup requested. Findings and fixes, all regression-scored by independent sub-agent reviews (7 rounds, final 10/10):

- [x] UI feedback for super export: real-time scan counters (every 100 files), staged messages (snapshot → scan → summarize), true percent progress on copy/cleanup, disabled-button reasons, migration conflict pre-warning, empty-target hint, conflict cards with per-head summaries and working resolve buttons (settings heads render choose-only; no draft).
- [x] Engine progress events structured (`commands.py`): phase/entry/scanned/done/completed/total/percent forwarded alongside the flat log message; preview emits stage messages; execute reuses one emitter.
- [x] Library lock: acquire with 3s queue instead of instant rejection; renderer pauses its 8s status polling while a transfer is busy (self-contention fix).
- [x] Plan persistence throttling (`transfer.py`): rewriting the ~37MB plan JSON after every copied file made a 2GB migration take hours; now saved at most every 50 entries / 5s plus forced at loop end. Resume re-verifies existing destination files, so throttling is safe.
- [x] Cleanup revalidation de-quadraticized (`transfer.py`): full-source revalidation (hash every remaining entry + root walk) once per source per pass instead of once per deleted file; per-file snapshot guard before unlink retained.
- [x] Settings materialization deadlock fixed (`settings.py`): apply() treated a missing local projection (fingerprint None) as a local-edit conflict, deadlocking all settings after migration activation; None now falls through to stage/materialize. Verified live: 129 settings applied, conflicts cleared.
- [x] Ghost settings conflict playbook: after resolve(), the marker can lag the merged head; align `settings_versions` marker + `refresh(capture=False)`. Documented in the dev skill.
- [x] Live results: preview 147s, copy+verify ~9 min, 12,370/12,370 verified, activation switched the library, counts available=308 / conflict=0, stale plans closed, old library archived as `library.migrated-backup-20260908` (activation-time capture in the old library correctly tripped the "new file since preview" guard; file verified merged into the new library, archive kept instead of deleting).
- [x] Tests: frontend 65/65; engine files compile; temp-library end-to-end migration+cleanup (state=completed, cleaned all managed entries, idempotent resume).

### Verification honesty note (2026-09-08, post-review)

- The local Windows venv lacks pytest, so tonight's engine changes (progress events, lock queue, plan-save throttling in all three loops incl. the episode-level execute branch, cleanup per-source cache, settings None-materialize fix) were verified locally by: py_compile on all touched files, fresh-process JSON-lines smoke, and temp-library end-to-end previews/executes (state=completed, idempotent resume). The 462-test pytest suite figure quoted above comes from the earlier delivery verification on the original environment, not from this machine tonight. Re-run the full pytest suite before the next packaged release.
- Old-library deletion criteria added to `doc/reference/resource-library.md` FAQ: open app → library location + connected badge, counts match pre-migration (308/0/0), one work detail + settings render correct; all three pass → delete. No open-ended "keep observing".
