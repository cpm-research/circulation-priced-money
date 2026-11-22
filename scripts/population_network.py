"""Write the wage network of one population draw as a small stored result, for the paper's network figure.

    python -X utf8 scripts/population_network.py [--map results/confirmation_quote] [--out results/population_network]

Each person pays one wage to one other person, drawn when the population is built. This script builds the
population of the map's first seed with the map's own settings and stores, for every person, whom it pays a wage
to, its spending weight, whether it holds a card and whether its income is business receipts. It builds the
population only: no day of the economy is run.
"""
import argparse
import dataclasses
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _folder in (ROOT, ROOT / "src"):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

from cpm_abm.economy_abm import Economy  # noqa: E402
from cpm_abm.engine.population import build_population  # noqa: E402
from scripts.paper_figures import stored_text  # noqa: E402

NOTE = ("The wage network of one population draw: for each person in order, wage_to (the person it pays a wage to), "
        "spending (its spending weight, mean 1), holder (it holds a card) and business (its income is business "
        "receipts). Built by cpm_abm.engine.population.build_population with the map's stored economy at the map's "
        "first seed; no day of the economy is run.")


def network(folder):
    """The stored record: the map's economy at its first seed, and the population's wage links and traits."""
    summary = json.loads(stored_text(folder, "summary.json"))
    names = {field.name for field in dataclasses.fields(Economy)}
    settings = {key: value for key, value in summary["economy"].items() if key in names}
    seed = int(summary["seeds"][0])
    economy = Economy(**{**settings, "seed": seed})
    people = build_population(economy)
    return dict(note=NOTE, map=Path(folder).name, seed=seed, n=int(economy.n),
                provenance=dict(git_commit=summary.get("provenance", {}).get("git_commit")),
                wage_to=people["wage_to"].astype(int).tolist(),
                spending=[round(float(value), 6) for value in people["spending"]],
                holder=people["holder"].astype(int).tolist(), business=people["business"].astype(int).tolist())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", type=Path, default=ROOT / "results" / "confirmation_quote",
                        help="the map whose economy and first seed the population is built with")
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "population_network", help="where it goes")
    args = parser.parse_args(argv)
    record = network(args.map)
    args.out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(record, separators=(",", ":"))
    # No time or file name in the header, so the same population gives the same bytes.
    with open(args.out / "network.json.gz", "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw,
                                                                         mtime=0) as packed:
        packed.write(text.encode("utf-8"))
    print(f"wrote {args.out / 'network.json.gz'}: {record['n']} people, seed {record['seed']}")


if __name__ == "__main__":
    main()
