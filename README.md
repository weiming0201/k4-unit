# K4 Unit — implementation candidate

A small, harness-neutral workspace for sourced requests, bounded task work,
checked writeback and recoverable self-maintenance. This is an isolated candidate,
not yet an independently accepted release. It does not launch an AI.

## What is installed

```text
workspace/
├── focus.md
├── manifest.json
├── receipts/                 # intents, compact results, frozen recovery kernels
├── archive/                  # created on first closure; optional for current use
└── projects/
    └── meta/
        ├── understanding/
        │   ├── description.md
        │   └── guide/README.md
        ├── object/
        │   ├── rules.md
        │   ├── workspace.json
        │   ├── skills/unit-{study,tend,reflect,revise}/SKILL.md
        │   └── mcp/{cli,server,loader,layout,storage,mechanics}.py
        ├── tools/adapter.py
        ├── pending/{understanding,target}/
        └── task/work/        # current.md exists only while a task is active
```

The four perspectives distinguish **understanding / maintenance** and
**another project / meta**. They are not four agents or a required execution
order. All ordinary projects have the same project structure.

Meta's purpose is reconstructing the stable configuration and capabilities of
this instance under declared dependencies. It is not Self in its entirety.
Stage one provides the generic seed; an adapter adds environment-specific
material. No assets, credentials, personalized identity, harness registrations,
runtime daemons or global configuration are installed by default.

One adapter installation is one meta target pending. Existing tools apply its
declared patch to object/tools and leave understanding pending for later
inspection by the attached AI. An adapter's claims are not automatically adopted
as self-knowledge. This candidate tests the generic local mechanism only; it
does not include Codex, pi or Claude Code adapters.

The distribution's installer also accepts `--source /installed/workspace`.
It checks that the source's shared upstream/adopted members and actual bytes
still match this verified distribution, then expands its neutral defaults.
Private guides, tools, assets, projects, pending, work and focus are not copied.
Changed shared members refuse before target writes. This needs the matching
distribution; it is neither a personalized backup restore nor a migration.
Source and target must be disjoint after parent-path normalization; equal,
ancestor or descendant locations refuse before staging or target writes.

## Entry points

- [Quickstart](QUICKSTART.md): install, check and the no-model adapter boundary.
- [API](API.md): five tools, CLI, pending/task and recovery inputs.
- [Rules](meta/object/rules.md): default semantic contract.
- `meta/object/mcp/layout.py`: mechanical structure definition; the installed
  `workspace.json` is its generated projection, not a second editable definition.

Python 3.12+ on POSIX is the intended support range. This candidate has so far
been exercised locally on macOS with Python 3.14; other platform/version claims
need their own results. Standard-library CLI needs no SDK. Optional MCP stdio
uses `mcp==1.23.3`; transport testing is not harness or model testing.

## Trust and verification

Verify a published package's externally provided digest before execution. An
installed checker detects drift relative to its readable baseline; mutable
code and baselines do not authenticate themselves. Checks do not prove task
correctness, authority or safe arbitrary replacement code.

The filesystem protocol is for one OS user and cooperating writers. It uses
bounded input, short locks, per-file CAS, durable intent and explicit recovery.
Process-crash tests do not establish all power-loss behavior or defense against
a malicious same-user race. Freeze/stop work writers before closing a task.

Archive is history, not a current execution dependency. Removing history loses
its source evidence, even when current operations remain usable. Receipts retain
compact results and request hashes indefinitely in this version; no automatic
expiry or snapshot garbage collection is promised.

Developer tests live in `tests/`; their passing results are not independent
acceptance. The release evidence must identify exact source hashes and every
remaining untested boundary. License: [MIT](LICENSE).
