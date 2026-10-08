# Quickstart

Choose an **absent or empty** target directory whose parent exists. Stage one
only expands files; it does not register skills/MCP or change harness settings.

```sh
python3 -I -S -B /absolute/package/install.py /absolute/new-workspace
python3 -I -S -B /absolute/new-workspace/projects/meta/object/mcp/cli.py \
  --workspace /absolute/new-workspace check --scope all
```

Paths containing spaces must be shell-quoted. Parent aliases are resolved;
the target itself may not be a symlink. Reinstalling an existing Unit is refused,
not an implicit update. Replacing an empty target changes its inode. Failure
may retain a sibling staging directory; inspect it before deciding its disposal.

After installation, the check and task CLI use only the installed copy. Default
`check --scope workspace` reads root metadata and receipt status, not project
payloads. Use `--scope project --project meta` or explicit `--scope all` when
deeper reading is intended.

To expand a neutral workspace with an installed instance as the source:

```sh
python3 -I -S -B /absolute/package/install.py /absolute/another-workspace \
  --source /absolute/existing-workspace
```

Keep the matching, externally verified distribution available for this command.
The installer inspects the instance's shared object baseline and bytes without
executing its code, then uses the matching distribution's defaults. It does not
export private focus, projects, pending, work, assets, guides or adapter changes.
Changed shared members refuse; a different distribution is not an implicit
upgrade. Self-check and normal task operations still need no source package.

## Adapter intake

The generic entry accepts an explicitly authorized local JSON package:

```sh
python3 -I -S -B /absolute/new-workspace/projects/meta/tools/adapter.py \
  --workspace /absolute/new-workspace \
  --package /absolute/adapter.json --request install-example-1
```

An adapter describes sources, one bounded object/tools patch with expected
SHA-256 values, and questions for new understanding pending. See [API](API.md).
There are no executable hooks or network retrievals. Supplying arbitrary
configuration bytes does not mean they have been loaded by a harness.

The operator must approve the patch and its real effects. A concrete future
harness adapter also needs binding/start/validation procedures, credentials
handling and actual runtime tests. None is supplied or run in stage one.
If a phase is interrupted, use its frozen recovery command or replay the same
adapter request; never substitute a new request ID to hide incomplete effects.

A determinate refusal is different from interruption. The error retains its
original code and includes `adapter_exits`. Package-determined reserved names
and unsupported structure changes are rejected before intake. If a started
task is refused without a durable close intent, choose either:

- Remove an authorized removable obstacle, then replay the original package
  with the original request ID.
- Explicitly abandon: run `adapter_exits.abandon.command` as an argument array,
  feeding JSON `adapter_exits.abandon.input` on stdin. This closes incomplete,
  preserves all selected pending and does not apply the patch. Only after this
  succeeds may a corrected package use a new request ID.

An already durable intent exposes only recovery, not abandonment. These exits
do not bypass corrupted frozen inputs. Preserve original `task/current.md` and
selected pending bytes in a trusted version/backup before editing elsewhere;
the default installer does not create a Git repository. A hash cannot restore
lost original bytes. See API recovery limits before attempting repairs.

## Optional MCP stdio

Use an existing or explicitly authorized isolated Python environment with
`mcp==1.23.3`. Keep it available as long as its interpreter is configured as
the stdio executable. The service command is:

```sh
/absolute/venv/bin/python -I -B \
  /absolute/new-workspace/projects/meta/object/mcp/server.py \
  --workspace /absolute/new-workspace
```

Do not add `-S` to this command: it needs the environment's installed SDK.
No registration example is automatically applied. Registration is a later
harness-specific operation, not evidence of successful model use. Restart a
resident service after adopting changes to its kernel; it must not bind new
tasks while its captured code differs from disk/adopted state.

The candidate's tests may create and kill only disposable fixture processes.
Do not run destructive recovery experiments against a working workspace.
