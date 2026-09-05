"""Separate current CPU processing from upstream-pinned CUDA inference."""
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def tool_config():
    config = json.loads((PROJECT / 'config/toolchain.json').read_text(encoding='utf-8'))
    local = PROJECT / 'config/toolchain.local.json'
    if local.exists():
        for name, values in json.loads(local.read_text(encoding='utf-8-sig')).items():
            config.setdefault(name, {}).update(values)
    return config


def tool_path(name, field='executable', workspace=None):
    config = tool_config()
    return Path(workspace or PROJECT.parent) / config[name][field]


def python_path(workspace=None, inference=False):
    key = 'inference_python' if inference else 'workflow_python'
    return tool_path(key, workspace=workspace)
