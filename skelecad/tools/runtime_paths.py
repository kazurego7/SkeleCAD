"""Separate current CPU processing from upstream-pinned CUDA inference."""
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def tool_path(name, field='executable', workspace=None):
    config = json.loads((PROJECT / 'config/toolchain.json').read_text(encoding='utf-8'))
    return Path(workspace or PROJECT.parent) / config[name][field]


def python_path(workspace=None, inference=False):
    key = 'inference_python' if inference else 'workflow_python'
    return tool_path(key, workspace=workspace)
