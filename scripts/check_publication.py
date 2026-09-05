"""Inspect Git's index, without reading ignored files or printing secrets."""
import ast
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = ('.tools/', 'legacy_prototypes/', 'skelecad/build/',
            'skelecad/backups/', 'skelecad/.runtime/', 'skelecad/assets/image_to_3d/')
PATTERNS = {
    'private key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'GitHub token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})',
    'Hugging Face token': rb'\bhf_[A-Za-z0-9]{25,}',
    'OpenAI token': rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}',
    'personal Windows path': rb'[A-Za-z]:[/\\]+Users[/\\]+(?!Public\b|Default\b)[A-Za-z0-9_.-]+',
    'private Tailscale hostname': rb'\b[a-zA-Z0-9-]+\.tail[a-f0-9]+\.ts\.net\b',
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main():
    entries = git('ls-files', '--stage', '-z').split(b'\0')
    errors, count, total = [], 0, 0
    for entry in entries:
        if not entry:
            continue
        metadata, raw_path = entry.split(b'\t', 1)
        mode, oid, stage = metadata.decode().split()
        name = raw_path.decode('utf-8')
        path = Path(name)
        count += 1
        if stage != '0' or mode not in ('100644', '100755'):
            errors.append(f'{name}: unresolved, symlink or submodule entry')
            continue
        if (name.startswith(EXCLUDED) or
                any(p in ('__pycache__', '.pytest_cache', '.venv', 'node_modules') for p in path.parts) or
                path.name.startswith('.env') and path.name != '.env.example' or
                path.suffix.lower() in ('.lnk', '.log', '.pem', '.key', '.p12', '.pfx', '.pyc') or
                path.name.endswith('.local.json')):
            errors.append(f'{name}: local/private file is staged')
        size = int(git('cat-file', '-s', oid))
        total += size
        if size > 10 * 1024 * 1024:
            errors.append(f'{name}: exceeds the 10 MiB source-publication limit')
            continue
        data = git('cat-file', 'blob', oid)
        if path.suffix.lower() in ('.png', '.jpg', '.blend'):
            continue
        for label, pattern in PATTERNS.items():
            if re.search(pattern, data):
                errors.append(f'{name}: {label} detected (value withheld)')
        try:
            if path.suffix == '.py':
                ast.parse(data.decode('utf-8-sig'), filename=name)
            elif path.suffix == '.json':
                json.loads(data.decode('utf-8-sig'))
        except (SyntaxError, ValueError) as exc:
            errors.append(f'{name}: invalid syntax ({type(exc).__name__})')
    if not count:
        errors.append('No staged/tracked files; stage the intended source files first.')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {count} indexed files, {total / 1024 / 1024:.2f} MiB; '
          'publication patterns and Python/JSON syntax checked.')
    print('Pattern scanning is not an exhaustive secret or license audit.')


if __name__ == '__main__':
    main()
