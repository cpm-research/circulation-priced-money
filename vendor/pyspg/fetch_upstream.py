"""Fetch the explicitly pinned public PySPG source; never run its CLI."""
from pathlib import Path
import base64
import hashlib
import json
import urllib.request

COMMIT = "2e6b4bb8512cd73838c190b8c9a616b7ebef188a"
REPOSITORY = "https://github.com/tessonec/PySPG"
ROOT = Path(__file__).resolve().parent
FILES = ["spg/base/iterator.py", "README.rst", "LICENCE", "spg/__init__.py", "VERSION", "setup.py"]
manifest = {"repository": REPOSITORY, "commit": COMMIT, "files": {},
            "role": "configuration enumeration outside monetary execution; not a rate solver"}
for relative in FILES:
    url = f"https://api.github.com/repos/tessonec/PySPG/contents/{relative}?ref={COMMIT}"
    request = urllib.request.Request(url, headers={"User-Agent": "ABM-PySPG-audit", "Accept": "application/vnd.github+json"})
    metadata = json.load(urllib.request.urlopen(request, timeout=30))
    content = base64.b64decode(metadata["content"])
    blob = hashlib.sha1(b"blob "+str(len(content)).encode()+b"\0"+content).hexdigest()
    if blob != metadata["sha"]:
        raise RuntimeError("GitHub blob integrity mismatch")
    destination = ROOT/"upstream"/relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    manifest["files"][relative] = {"github_blob_sha": blob, "sha256": hashlib.sha256(content).hexdigest(),
                                  "url": url, "bytes": len(content)}
(ROOT/"upstream_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps({"commit": COMMIT, "files": manifest["files"]}, indent=2))
