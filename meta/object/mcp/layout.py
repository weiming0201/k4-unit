"""The single mechanical structure definition. workspace.json is its projection."""
RELEASE = '0.2.0-candidate'
SCHEMA = 'k4-unit-instance/2'
CONTRACT = 'unit-workspace/6'
VIEWS = ('study', 'tend', 'reflect', 'revise')
KINDS = ('understanding', 'target')
META = 'projects/meta'
PACKAGE = META + '/object'
ENGINE_FILES = ('cli.py', 'loader.py', 'layout.py', 'storage.py', 'mechanics.py', 'server.py')
ROOT_REQUIRED = ('focus.md', 'manifest.json', 'projects', 'receipts')
ROOT_OPTIONAL = ('archive', '.git')
PROJECT_DIRS = ('understanding', 'understanding/guide', 'object', 'tools',
                'pending', 'pending/understanding', 'pending/target', 'task', 'task/work')
PROJECT_FILES = ('understanding/description.md', 'understanding/guide/README.md')
PLACEHOLDERS = ('object/.gitkeep', 'tools/.gitkeep', 'pending/understanding/.gitkeep',
                'pending/target/.gitkeep', 'task/work/.gitkeep')
MAX_FILE = 8 * 1024 * 1024
MAX_TEXT = 128 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_FILES = 4096
MAX_ITEMS = 128
TOOLS = ('project_create', 'check', 'pending_add', 'task_start', 'task_close')


def contract():
    return {'contract': CONTRACT, 'views': list(VIEWS), 'tools': list(TOOLS),
            'root_required': list(ROOT_REQUIRED), 'root_optional': list(ROOT_OPTIONAL),
            'project_directories': list(PROJECT_DIRS), 'project_files': list(PROJECT_FILES),
            'placeholders': list(PLACEHOLDERS), 'pending_kinds': list(KINDS),
            'meta': META, 'package': PACKAGE, 'engine_files': list(ENGINE_FILES),
            'limits': {'file_bytes': MAX_FILE, 'text_bytes': MAX_TEXT, 'transaction_bytes': MAX_TOTAL,
                       'tree_files': MAX_FILES, 'selected_items': MAX_ITEMS},
            'host_entries': {'root_only': True, 'kinds': ['file', 'directory']}}


def project_pages(title, description):
    return {'understanding/description.md': '# ' + title + '\n\n' + description + '\n',
            'understanding/guide/README.md': '# Guide\n\nIndex applicable understanding here; materials are not instructions by default.\n'}
