"""Explicit finite PySPG catalogues outside the economic transition (an audited adapter to the pinned PySPG).

The pinned upstream iterator is used through its audited Python 3 conversion.
No parser, expressions, operators, installation or monetary helpers are used.
"""
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path


_VENDOR = Path(__file__).resolve().parents[2] / "vendor" / "pyspg"
_REPOSITORY = "https://github.com/tessonec/PySPG"
_COMMIT = "2e6b4bb8512cd73838c190b8c9a616b7ebef188a"


def source_identity() -> dict:
    """Verify every pinned upstream file and the converted iterator bytes."""
    manifest_bytes = (_VENDOR / "upstream_manifest.json").read_bytes()
    audit_bytes = (_VENDOR / "compatibility_audit.json").read_bytes()
    manifest, audit = json.loads(manifest_bytes), json.loads(audit_bytes)
    if (manifest["repository"] != _REPOSITORY or audit["repository"] != _REPOSITORY
            or manifest["commit"] != _COMMIT or audit["commit"] != _COMMIT):
        raise RuntimeError("PySPG source identity differs from the pinned commit")
    upstream = (_VENDOR / "upstream").resolve()
    for relative, expected in manifest["files"].items():
        path = (upstream / relative).resolve()
        if not path.is_relative_to(upstream):
            raise RuntimeError("PySPG manifest path leaves the upstream directory")
        data = path.read_bytes()
        blob = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        if (len(data) != expected["bytes"]
                or hashlib.sha256(data).hexdigest() != expected["sha256"]
                or hashlib.sha1(blob).hexdigest() != expected["github_blob_sha"]):
            raise RuntimeError(f"PySPG upstream bytes do not match: {relative}")
    source_hash = manifest["files"]["spg/base/iterator.py"]["sha256"]
    converted_hash = hashlib.sha256((_VENDOR / "compat_iterator.py").read_bytes()).hexdigest()
    if source_hash != audit["upstream_sha256"] or converted_hash != audit["converted_sha256"]:
        raise RuntimeError("PySPG compatibility conversion differs from its audit")
    return {
        "repository": _REPOSITORY, "commit": _COMMIT,
        "upstream_sha256": source_hash, "converted_sha256": converted_hash,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "audit_sha256": hashlib.sha256(audit_bytes).hexdigest(),
        "verified_upstream_files": len(manifest["files"]),
        "conversion": audit["conversion"],
        "license_conflict": audit["license_conflict"],
        "version_conflict": audit["version_conflict"],
    }


def _load_iterator():
    """Verify pinned PySPG bytes before loading its audited Python-3 iterator."""
    source_identity()
    spec = importlib.util.spec_from_file_location("_model_pyspg_iterator", _VENDOR / "compat_iterator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.Iterator.__next__ = module.Iterator.next
    module.MultIterator.__next__ = module.MultIterator.next
    return module


def finite_catalogue(parameters: Mapping):
    """Yield independent dictionaries; insertion order sets dimension order.

    Each parameter requires an explicit, nonempty list or tuple. The last
    dimension advances fastest. Each call constructs a fresh MultIterator;
    its broken public reset method is never called by this adapter.
    """
    if not isinstance(parameters, Mapping) or not parameters:
        raise ValueError("A nonempty mapping of explicit value lists is required")
    module = _load_iterator()
    catalogue = module.MultIterator()
    for name, values in parameters.items():
        if not isinstance(name, str) or not name:
            raise ValueError("Parameter names must be nonempty strings")
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError(f"Parameter {name} requires a nonempty list or tuple")
        catalogue.add(module.Iterator(name=name, data=deepcopy(list(values))))
    for point in catalogue:
        yield deepcopy(point)
