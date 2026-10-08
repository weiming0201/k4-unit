"""Optional MCP stdio transport over the same captured Unit kernel."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True)
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('_unit_cli',Path(__file__).resolve().with_name('cli.py'))
    cli=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    package=cli.load_kernel(args.workspace)
    unit=package.mechanics.Unit(args.workspace)
    from mcp.server.fastmcp import FastMCP
    server=FastMCP('k4-unit')

    def invoke(tool, values):
        try:
            return unit.call(tool,values)
        except Exception as e:
            return e.report() if hasattr(e,'report') else dict(ok=False,code='input-or-io',detail=str(e))

    @server.tool()
    def check(scope: str='workspace',project: str|None=None) -> dict:
        """Read-only workspace/project/all check; does not repair or prove semantics."""
        return invoke('check',dict(scope=scope,project=project))

    @server.tool()
    def project_create(title: str,description: str,request_id: str) -> dict:
        """Create and register one neutral project. Same request can be replayed."""
        return invoke('project_create',dict(title=title,description=description,request_id=request_id))

    @server.tool()
    def pending_add(project: str,kind: str,source_refs: list[str],body: str,
                    request_id: str,files: dict[str,str]|None=None) -> dict:
        """Append a candidate (optional base64 attachments), not an adopted fact."""
        return invoke('pending_add',dict(project=project,kind=kind,source_refs=source_refs,body=body,request_id=request_id,files=files))

    @server.tool()
    def task_start(project: str,selected: list[dict],task: str,write_scopes: list[str],request_id: str) -> dict:
        """Bind selected pending versions, frozen purpose/scope and an old kernel."""
        return invoke('task_start',dict(project=project,selected=selected,task=task,write_scopes=write_scopes,request_id=request_id))

    @server.tool()
    def task_close(project: str,task_id: str,baseline: str,outcome: str,dispositions: dict[str,str],
                   checks: list[str],transcript_refs: list[str],request_id: str,
                   writes: list[dict]|None=None,new_pending: list[dict]|None=None) -> dict:
        """Freeze dispositions, apply authorized local payloads, archive and release task."""
        return invoke('task_close',dict(project=project,task_id=task_id,baseline=baseline,outcome=outcome,
            dispositions=dispositions,checks=checks,transcript_refs=transcript_refs,request_id=request_id,
            writes=writes,new_pending=new_pending))

    server.run(transport='stdio')


if __name__=='__main__':
    main()
