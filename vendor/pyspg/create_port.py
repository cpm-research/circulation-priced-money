"""Audited syntax-only conversion; iterator protocol aliases stay in adapter."""
from pathlib import Path
import difflib
import hashlib
import json
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from lib2to3.refactor import RefactoringTool

ROOT = Path(__file__).resolve().parent
original = ROOT/"upstream"/"spg"/"base"/"iterator.py"
manifest = json.loads((ROOT/"upstream_manifest.json").read_text(encoding="utf-8"))
expected = manifest["files"]["spg/base/iterator.py"]["sha256"]
source_bytes = original.read_bytes()
if hashlib.sha256(source_bytes).hexdigest() != expected:
    raise RuntimeError("pinned upstream source hash changed")
source = source_bytes.decode("utf-8")
fixers = ["lib2to3.fixes.fix_print"]
converted = str(RefactoringTool(fixers).refactor_string(source, str(original)))
compile(converted, "compat_iterator.py", "exec")
(ROOT/"compat_iterator.py").write_bytes(converted.encode("utf-8"))
diff = "".join(difflib.unified_diff(source.splitlines(keepends=True), converted.splitlines(keepends=True),
                                  fromfile="upstream/iterator.py", tofile="compat_iterator.py"))
(ROOT/"compat.diff").write_text(diff, encoding="utf-8")
audit = {"repository": manifest["repository"], "commit": manifest["commit"],
         "upstream_sha256": expected, "converted_sha256": hashlib.sha256(converted.encode()).hexdigest(),
         "conversion": "Python 3.12 lib2to3 fix_print only; no change to iterator state/advance logic",
         "fixers": fixers, "protocol_aliases": "experiments.py aliases Iterator/IterConstant/MultIterator.__next__ to original next",
         "license_conflict": "iterator.py header says GNU/GPL Version 2; repository LICENCE and setup classifier say GPLv3; originals retained verbatim",
         "version_conflict": "VERSION says 4.0.0; spg/__init__.py says 4.0.1; neither is an installed-version claim",
         "scope": "Iterator and MultIterator explicit finite value lists only; parser, CLI, mutable operators and eval paths are unused"}
(ROOT/"compatibility_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
print(diff)
print(json.dumps(audit, indent=2))
