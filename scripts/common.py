"""Shared bounded I/O and provenance helpers (Python 3.10+)."""
import hashlib
import json
import os
import tempfile
from pathlib import Path

VERSION = "0.2.0"


def contained_path(root, relative):
    root = Path(root).resolve()
    relative = str(relative)
    if "\\" in relative or ":" in relative or Path(relative).is_absolute():
        raise ValueError(f"不允许绝对路径或非可移植路径：{relative}")
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"路径超出允许目录：{relative}")
    return target


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data.encode("utf-8") if isinstance(data, str) else data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_hashes(root):
    root = Path(root)
    if root.is_symlink():
        raise ValueError("源码目录不能是符号链接")
    if not root.is_dir():
        return {}
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"源码目录含符号链接：{path.name}")
        if path.is_file():
            contained_path(root, path.relative_to(root))
            result[path.relative_to(root).as_posix()] = sha256_file(path)
    return result
