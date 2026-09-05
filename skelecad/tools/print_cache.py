"""Print preparation identity, including effective app paths and native presets."""
import hashlib
import json
from pathlib import Path
from runtime_paths import PROJECT, tool_config


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_context(reports):
    config = tool_config()
    bambu = config['bambu_studio']
    profiles = Path(bambu['profiles'])
    value = {
        'plates': reports,
        'parameters': digest(PROJECT/'config/parameters.json'),
        'toolchain': config,
        'bambu': {key: digest(Path(bambu[key])) for key in ('executable', 'library')},
        'presets': {str(p.relative_to(profiles)): digest(p) for p in sorted(profiles.rglob('*.json'))},
        'code': {str(p.relative_to(PROJECT)): digest(p) for folder in ('src', 'tools')
                 for p in sorted((PROJECT/folder).glob('*.py'))},
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
