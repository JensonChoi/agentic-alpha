"""Canonical checksums shared by immutable inputs and persisted runs."""
import hashlib
import json
import subprocess


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def code_revision() -> str:
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return 'unavailable'


def implementation_hash() -> str:
    """Identify execution code even before the working branch is committed."""
    from pathlib import Path
    root=Path(__file__).parent
    return digest({path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.glob('*.py'))})
