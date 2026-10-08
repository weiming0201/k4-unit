# Local interfaces

All mutation calls bind one workspace and one `request_id` (1–64 lowercase
ASCII letters/digits/underscore/hyphen). Same ID and identical JSON content
returns the original result. JSON key order is ignored; array order and supplied
arguments are significant. Same ID with different content or operation refuses.
Omitted optional fields and explicit null are currently distinct request inputs;
repeat the original form. None of these fields supplies semantic authorization.

CLI tools accept UTF-8 JSON, bounded to 32 MiB:

```sh
python3 -I -S -B /workspace/projects/meta/object/mcp/cli.py \
  --workspace /workspace call pending_add --input /path/request.json
```

`--input -` reads stdin. Success exits 0, refusal/failure exits 1 with JSON.
An SDK stdio call returns the same mechanical result. Five tools:

| Tool | Inputs in addition to request_id | Effect |
| --- | --- | --- |
| project_create | title, description | Number and register one neutral project |
| check | scope=workspace/project/all; project ID for project scope; no request_id | Read-only issues, scoped baselines, lightweight task index |
| pending_add | project, kind=understanding/target, source_refs, body, optional files | Append one immutable candidate; files maps relative names to base64 bytes |
| task_start | project, selected, task, write_scopes | Claim one active slot and freeze selected item versions, current.md and kernel |
| task_close | project, task_id, baseline, outcome, dispositions, checks, transcript_refs, optional writes/new_pending | Checked writeback, disposition, archive, slot release |

`selected` is a nonempty list of `{id, kind, sha256}` returned by pending_add.
`task` states purpose, acceptance, authority and next action expectations in
free text. The tool checks that it is bounded/nonempty, not that it is good.
`write_scopes` are project-relative paths in understanding/object/tools; an
empty list is legal for read-only work. `current.md` is frozen until closure.

The task_start result's `baseline` identifies its full active binding; task_close
must repeat it. `dispositions` maps exactly the selected IDs to `done` or
`remaining`. `outcome` is `completed` only if all are done, otherwise `incomplete`.
`checks` is a nonempty list of evidence/verification descriptions or references;
`transcript_refs` can be empty. A truthful negative answer can complete an
investigation but does not make an unperformed requested implementation done.

Each write is `{path, from_work}`. `path` lies inside the frozen write scopes;
`from_work` is a path inside this task's work, or null to delete a previously
existing file. The original per-file baseline is compared only for touched
files. New incoming pending does not invalidate the task. New pending entries
use pending_add's content fields (not request_id) and may name other registered
projects; this appends candidates without editing their active tasks.

## Recovery and version identity

The old kernel snapshot is complete before publishing a transaction intent.
Unfinished intents retain frozen payload and step progress. CAS accepts only
the expected before or this transaction's after state; other versions refuse.
After local writeback, archival and manifest projection finish, one atomic
replacement marks the receipt complete and removes its raw payload. Same-request
replay then requires neither work nor archive. No request expiry is implemented.

Checks report unfinished requests with an argv recovery command, for example:

```sh
python3 -I -S -B /workspace/receipts/engines/DIGEST/cli.py \
  --workspace /workspace recover --request REQUEST
```

Current entry mutation requires loaded=disk=adopted kernel identity. An explicit
snapshot may close a task bound to it, or resume its existing frozen intent;
it cannot create new tasks/projects/pending. Interpreter version is recorded;
a version difference is not evidence of compatibility. Snapshot bytes are a
recovery dependency, not a second current object or a signature.

Structural definition is declarative in layout.py; workspace.json is generated
from it. Compatible internal kernel changes are allowed. This version does not
implement cross-contract migration. A changed declaration/projection with other
active tasks is rejected explicitly as stranding their old contracts. Static
declaration inspection cannot prove arbitrary replacement Python semantics;
source and behavioral review remain required.

An `active-old-contract` refusal retains `projects` and also returns `tasks`
with each affected `project`, `task_id` and bound `engine`. The reserved
`unit-` skill namespace includes empty directories; meta/all checks and meta
object adoption reject additional reserved names. Workspace-only checks remain
shallow and do not inspect skill directories.

## Generic adapter package

```json
{
  "description": "Install an inert example configuration",
  "source_refs": ["external source identifier"],
  "patch": [
    {"path": "object/example.txt", "before": null, "content": "ZXhhbXBsZQo="}
  ],
  "understanding": ["Observe whether and how this configuration is actually loaded."]
}
```

`before` is the previous SHA-256 or null for an absent file; `content` is base64
or null for deletion. Paths are only meta object/tools. One installation request
(at most 48 ID characters) uses deterministic `-intake`, `-start`, `-close`
phase IDs. Intake is one target pending with the frozen package as attachment.
Stale patches remain candidates, not partially adopted changes. Recognition
questions become new understanding pending only on successful closure; no
understanding body is overwritten. No code in a package is executed as an
install hook. If the adapter entry itself is being replaced, keep access to a
trusted copy of the old wrapper; the core's printed snapshot recovery command
remains the authority for an interrupted close.

## Bounds and claim limits

Single payload file: 8 MiB. Semantic string: 128 KiB. Request/transaction raw
payload: 32 MiB. Adapter JSON package: 4 MiB. Selected items, writes or new
pending per close: 128 each. Inspected tree: 4096 files and 32 MiB. Large objects
should use authorized external references. Metadata also obeys finite bounds.

Managed paths reject traversal and symlinks. `host_entries` is an open root
manifest map of root names to `file`/`directory`; it declares shape, not binding
or authority. It must not replace reserved root entries; .git is already known.
No automatic registration/unregistration or .DS_Store deletion occurs.

Checks do not repair, repin, approve facts or authenticate their own code.
The protocol supports cooperating local single-user processes, not hostile
same-user writers or arbitrary distributed transactions. Work writers must be
stopped before archival. Root manifest and receipts are mechanically maintained;
manual editing of those transaction fields is not recovery.

## Refused adapters and explicit exits

`adapter_exits` is advisory, read-only output alongside the original error; no
exit is automatically executed. `state` distinguishes `not-started`,
`active-refused`, `recover-intent`, `completed`, `no-longer-active`, and `unknown`.
For `active-refused`, `retry` names the same request and `abandon` supplies an
old-bound CLI argument array plus JSON `input` for stdin. The abandonment phase
ID is the installation ID plus `-abandon`; do not allocate any derived phase ID
to an unrelated operation. Abandonment itself may be replayed if interrupted.

The old kernel still checks frozen inputs, task identity, baseline, locks and
unfinished intents. Therefore an offered command is not a guarantee that a
later invocation will succeed. A concurrent change can make it refuse. When
any intent is unfinished, only its frozen `recover` commands are offered; never
cancel or supersede a partially applied transaction. Errors reading the state
retain the primary refusal and report exit state unknown, not a safe escape.

After explicit incomplete closure, an original adapter request cannot be
reopened. A corrected package uses a new ID; the old selected candidate remains
pending, not done. This version has no `declined` disposition. It cannot remove
an unperformed implementation request by pretending it was completed.

The adapter reuses the kernel's reserved-name and declared-structure rules
before intake. This does not replace close-time CAS or environmental checks.
Each generated understanding item begins with the fixed label
`Adapter-provided, unverified. Observe before adoption.` and cites the original
package SHA-256. Original questions or assertions remain attributed material;
labels and mechanical installation do not validate their content. Generated
text and added source references are limit-checked before intake.

If frozen `current.md` or selected pending bytes were changed, even incomplete
closure refuses. Restore exact original bytes only from a trusted version,
original input or backup; receipts contain hashes, not those recoverable bytes.
Without original bytes, this version has no supported force-close. Preserve the
conflict for a separately designed recovery; do not repin manifest fields.

Replacing kernel or adapter source remains a trust-root change requiring
external review. There is no new permission switch, automatic behavioral test,
preimage backup of arbitrary target files, or complete uninstall in this version.
