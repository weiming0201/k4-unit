"""Actual SDK stdio discovery/calls; no harness registration and no model."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
sys.dont_write_bytecode=True
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

SOURCE=Path(__file__).resolve().parents[1]


class StdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_five_tools_from_installed_copy_without_source(self):
        with tempfile.TemporaryDirectory(prefix='unit-stdio-') as tmp:
            root=Path(tmp)
            package=root/'package'
            shutil.copytree(SOURCE,package)
            spec=importlib.util.spec_from_file_location('fixture_install',package/'install.py')
            installer=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(installer)
            ws=root/'ws'
            self.assertTrue(installer.install(ws)['ok'])
            package.rename(root/'source-withdrawn')
            params=StdioServerParameters(command=sys.executable,args=['-I','-B',
                str(ws/'projects/meta/object/mcp/server.py'),'--workspace',str(ws)],
                cwd=str(root),env={'PATH':os.defpath,'PYTHONIOENCODING':'utf-8'})
            async with asyncio.timeout(30):
                async with stdio_client(params) as (read,write):
                    async with ClientSession(read,write) as client:
                        await client.initialize()
                        tools=await client.list_tools()
                        self.assertEqual({t.name for t in tools.tools},
                            {'check','project_create','pending_add','task_start','task_close'})
                        async def call(name,args):
                            result=await client.call_tool(name,args)
                            self.assertFalse(result.isError,result)
                            value=result.structuredContent
                            if value is None:
                                value=json.loads(result.content[0].text)
                            self.assertTrue(value['ok'],value)
                            return value
                        await call('check',{'scope':'all'})
                        project=await call('project_create',dict(title='stdio fixture',description='Real protocol test',request_id='project'))
                        item=await call('pending_add',dict(project=project['project'],kind='target',source_refs=['test'],body='Read-only task',request_id='pending'))
                        started=await call('task_start',dict(project=project['project'],selected=[{k:item[k] for k in ('id','kind','sha256')}],
                            task='Check installed protocol behavior without changing object.',write_scopes=[],request_id='start'))
                        args=dict(project=project['project'],task_id=started['task_id'],baseline=started['baseline'],outcome='completed',
                            dispositions={item['id']:'done'},checks=['Actual protocol assertions'],transcript_refs=[],request_id='close')
                        closed=await call('task_close',args)
                        self.assertEqual(closed,await call('task_close',args))
                        await call('check',{'scope':'all'})


if __name__=='__main__':
    unittest.main(verbosity=2)
