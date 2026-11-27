"""Copy a finished run's stores into results/, compressed, in the form the paper's scripts read; list and check them.

    python scripts/pack_results.py <run folder> <name> [--into results] [--stores ...] [--limit-mb 50]
    python scripts/pack_results.py --sums  [--into results]
    python scripts/pack_results.py --check [--into results] [--complete]

Packing copies summary.json, cells.json and measures.json (each that the run folder holds; summary.json is required)
to <into>/<name>/<store>.json.gz, the bytes unchanged inside. failure_counts.json is copied only when --stores names
it; the runner's own figures are not copied. The compressed files carry no time and no file name, so the same store
gives the same bytes on every machine. Each copy is read back and compared with the original before the script
reports it. It runs no simulation.

No file written is larger than the limit (50 MB: GitHub warns above 50 MiB and refuses a file above 100 MiB). A store
whose compressed copy would be larger is written as volumes, <store>.json.gz.1of6 to .6of6: the store's bytes cut
into equal slices, each slice a complete gzip stream. The volumes joined in order are a gzip file of the whole store
(``cat measures.json.gz.*of* > measures.json.gz``), and the paper's scripts read the volumes as they are.

A run made one seed a part (scripts/run_confirmation.py) also has its records copied, as text, into
<into>/<name>/run_records/: the command, the progress log, the join's record, each part's integrity checks and,
where a seed could not finish its run, the record of the seeds set aside.

--sums writes <into>/SHA256SUMS, the SHA-256 of every data file under <into> (each compressed store or volume and
each run record; the cards and the README are written from them and are not listed) in the format of
``sha256sum``, sorted by path. --check reads that list and compares every listed file that is present; a listed
file that is absent is reported (the largest stores may be kept in an archive, not in the repository; see
results/README.md) and fails the check only with --complete. A data file present but not listed is reported and
never fails the check.
"""
import argparse
import gzip
import hashlib
import io
import re
import shutil
import sys
from pathlib import Path

STORES = ("summary.json", "cells.json", "measures.json")    # what results/ ships of a run, in this order
LIMIT_MB = 50                                               # no file written is larger, in megabytes of 10^6 bytes
VOLUME = re.compile(r"\.gz\.(\d+)of(\d+)$")                 # a volume's name ends .gz.<k>of<n>
DATA = re.compile(r"\.gz(\.\d+of\d+)?$")                   # a compressed store, whole or a volume
SUMS = "SHA256SUMS"                                         # the list of checksums, at the top of results/
# A run in parts: its records at the top of the run folder. set_aside.json is there only when a seed could not finish.
RECORDS = ("command.json", "progress.txt", "joined.json", "set_aside.json")


def packed(data):
    """``data`` compressed at the highest level, with no time and no file name in the header."""
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, compresslevel=9, mtime=0) as out:
        out.write(data)
    return buffer.getvalue()


def volumes(data, limit):
    """``data`` compressed into as few equal slices as keeps every slice at most ``limit`` bytes compressed: a list of
    gzip streams whose contents, joined in order, are ``data``. One stream when the whole fits."""
    whole = packed(data)
    if len(whole) <= limit:
        return [whole]
    count = -(-len(whole) // limit)                          # at least this many, since slices compress alike
    while True:
        size = -(-len(data) // count)
        blobs = [packed(data[start:start + size]) for start in range(0, len(data), size)]
        if max(map(len, blobs)) <= limit:
            return blobs
        count += 1


def volume_names(name, count):
    """The file names of a store shipped in ``count`` volumes: name.gz alone, else name.gz.<k>of<count>, the k padded
    with zeros so the names sort in order."""
    if count == 1:
        return [name + ".gz"]
    width = len(str(count))
    return [f"{name}.gz.{k:0{width}d}of{count}" for k in range(1, count + 1)]


def shipped(folder, name):
    """The files a store is shipped as in ``folder``, in order: [name.gz], its volumes, or [] when it is not there.
    Raises when the volumes present are not the whole set their names declare."""
    folder = Path(folder)
    if (folder / (name + ".gz")).exists():
        return [folder / (name + ".gz")]
    found = sorted((int(m.group(1)), int(m.group(2)), p) for p in folder.glob(name + ".gz.*of*")
                   if (m := VOLUME.search(p.name)))
    if found and [(k, n) for k, n, _ in found] != [(k, len(found)) for k in range(1, len(found) + 1)]:
        raise ValueError(f"{folder}: the volumes of {name} are not a whole set: {[p.name for _, _, p in found]}")
    return [p for _, _, p in found]


def unpacked(folder, name):
    """The bytes of a store shipped in ``folder`` (one file or volumes), or None when it is not there."""
    files = shipped(folder, name)
    return b"".join(gzip.decompress(p.read_bytes()) for p in files) if files else None


def pack(run, target, stores=STORES, limit=LIMIT_MB * 10**6):
    """Copy the stores of the run folder ``run`` into ``target`` compressed, none over ``limit`` bytes a file, and the
    records of a run made in parts; returns the names written."""
    run, target = Path(run), Path(target)
    if not (run / "summary.json").exists():
        raise FileNotFoundError(f"{run} holds no summary.json: not a finished run")
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for name in stores:
        if (run / name).exists():
            written += _pack_store(run, name, target, limit)
    return written + _records(run, target)


def _pack_store(run, name, target, limit):
    """Copy the store ``name`` of ``run`` into ``target`` compressed in volumes of at most ``limit`` bytes, replacing
    any earlier copy (which may have had another number of volumes); returns the volumes' names. Refused unless the copy
    reads back to the original."""
    source = run / name
    data = source.read_bytes()
    blobs = volumes(data, limit)
    for old in shipped(target, name):
        old.unlink()
    names = volume_names(name, len(blobs))
    for file_name, blob in zip(names, blobs):
        (target / file_name).write_bytes(blob)
    if unpacked(target, name) != data:                   # never ship a copy that does not read back
        raise ValueError(f"{source}: the compressed copy does not read back to the original")
    return names


def _records(run, target):
    """Copy the records of a run made one seed a part into ``target``/run_records: the command, the progress log, the
    join's record and each part's integrity checks. Nothing for a run made in one go."""
    parts = sorted((run / "parts").glob("seed_*/integrity.json")) if (run / "parts").is_dir() else []
    if not parts:
        return []
    out = target / "run_records"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    copies = [(run / name, out / name) for name in RECORDS if (run / name).exists()]
    copies += [(p, out / f"integrity_{p.parent.name}.json") for p in parts]
    for source, copy in copies:
        # Text records, written with LF line ends on every system, so a record's checksum is the same wherever
        # the repository is checked out.
        copy.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
    return [f"run_records/{copy.name}" for _, copy in copies]


def digest(path):
    """The SHA-256 of a file, read a block at a time."""
    found = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            found.update(block)
    return found.hexdigest()


def listed_files(into):
    """Every data file under ``into`` (a compressed store or volume, or a run's record), as paths relative to it,
    sorted."""
    into = Path(into)
    return sorted(p.relative_to(into).as_posix() for p in into.rglob("*")
                  if p.is_file() and (DATA.search(p.name) or p.parent.name == "run_records"))


def write_sums(into):
    """Write ``into``/SHA256SUMS over every data file under ``into``; returns how many files it lists."""
    into = Path(into)
    names = listed_files(into)
    lines = [f"{digest(into / name)}  {name}" for name in names]
    (into / SUMS).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(names)


def check_sums(into):
    """Compare the data files under ``into`` with its SHA256SUMS: the names verified, absent, changed and not
    listed."""
    into = Path(into)
    lines = (into / SUMS).read_text(encoding="utf-8").splitlines()
    listed = {name: value for value, name in (line.split("  ", 1) for line in lines if line)}
    here = set(listed_files(into))
    verified, absent, changed = [], [], []
    for name, value in sorted(listed.items()):
        if name not in here:
            absent.append(name)
        else:
            (verified if digest(into / name) == value else changed).append(name)
    return verified, absent, changed, sorted(here - set(listed))


def main(argv=None):
    """The command line: pack one run folder under a name, or write or check the list of checksums."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path, nargs="?", help="the run folder as the population runner wrote it")
    parser.add_argument("name", nargs="?", help="the folder name under results/")
    parser.add_argument("--into", type=Path, default=Path(__file__).resolve().parents[1] / "results",
                        help="where the results folders are (default: the repository's results/)")
    parser.add_argument("--stores", nargs="+", default=list(STORES), help="the stores copied (default: summary.json, "
                        "cells.json, measures.json; failure_counts.json only when named)")
    parser.add_argument("--limit-mb", type=float, default=LIMIT_MB, help="the largest file written, megabytes")
    parser.add_argument("--sums", action="store_true", help="write the list of checksums of everything under --into")
    parser.add_argument("--check", action="store_true", help="compare the files under --into with the list")
    parser.add_argument("--complete", action="store_true", help="with --check: a listed file that is absent fails")
    args = parser.parse_args(argv)
    if args.check:
        verified, absent, changed, unlisted = check_sums(args.into)
        print(f"{args.into}: {len(verified)} files verified, {len(absent)} absent, {len(changed)} changed, "
              f"{len(unlisted)} not listed")
        for label, names in (("changed", changed), ("absent", absent), ("not listed", unlisted)):
            if names:
                print("\n".join(f"  {label}: {name}" for name in names))
        return 1 if changed or (args.complete and absent) else 0
    if args.sums:
        print(f"{args.into / SUMS}: {write_sums(args.into)} files")
        return 0
    if args.run is None or args.name is None:
        parser.error("give a run folder and a name, or --sums, or --check")
    written = pack(args.run, args.into / args.name, args.stores, int(args.limit_mb * 10**6))
    print(f"{args.into / args.name}: {', '.join(written)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
