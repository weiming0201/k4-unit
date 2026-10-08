# K4 Unit v0.2.0-rc.1 — frozen prerelease

This release freezes the reviewed, harness-neutral Unit implementation. It is
a workspace seed and local maintenance mechanism, not a running AI or a hosted
service. License: MIT. The internal package label remains `0.2.0-candidate`.

All 30 product files are byte-identical to the reviewed r4 source. The original
README is retained as part of that snapshot: its statements that independent
review is pending and that testing is Mac-only describe the earlier submission
time. The status below supersedes those release-status sentences only; no
product contract or behavior has been changed.

## Included

- Neutral workspace installation with nonempty meta, four responsibility views,
  per-project understanding/object/tools/pending/task/work, and archive.
- Five deterministic operations: project_create, check, pending_add, task_start,
  task_close; CLI and optional MCP stdio entry points.
- CAS checks, bounded inputs, cooperative locks, recoverable task closure,
  frozen old-kernel recovery and generic declarative adapter application.
- A generic adapter interface, not concrete Codex, pi or Claude Code adapters.

## Verification and provenance

The reviewed r4 source passed 83 local tests on macOS/Python 3.14.3 and three
storage measurements. Independent Linux/Python 3.14.4 review repeated 83 tests
and three measurements, and exercised nine additional path probes. The r4
independent review reported no blockers for the mechanical implementation.
These are prior results bound to unchanged source, not a new test run at release.

- Private review manifest SHA-256:
  `53e4d9ea1eb5492eb203d29201311da14e816e883014f72bf7ef3606b1eced85`
- Independent r4 report SHA-256:
  `006d0d385aafc1e08cad07214b038dd492fc0e1e40d3b5e61fb780cace1c393f`
- `SOURCE-SHA256SUMS` lists only the 30 public product files. The private review
  bundle, local paths, raw logs and conversations are not distributed. Hashes
  identify those private records but do not make them publicly reproducible.
- The repository's `.k4/resource.json` is development repository identity
  metadata. It is not an installed-workspace `.k4` wrapper and is absent from
  the installable source archive.

## Limits

No real harness/model loading, deployment, live configuration migration or
personalized full restore is claimed. Python 3.12+ is the intended range, but
the full 83-test candidate suite has not been verified on 3.12. The filesystem
contract assumes one OS user and cooperative POSIX writers; it is not a sandbox
against a hostile same-user process and does not prove power-loss safety.
Case-insensitive filesystem aliases and bind-mount aliases remain unverified.
Local supplementary stdio recovery and audit-hook probes were not independently
rerun in r4. No automatic receipt expiry or kernel garbage collection is promised.

Cross-project permissions and one-hop attention policies are design inputs for
a later version; this release does not enforce them. The included tests and CLI
allow inspection of the published behavior. Check the release asset digest
before execution, then use QUICKSTART.md; no global harness setup is automatic.
