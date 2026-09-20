"""Compare every Census geography field and CSV cell without promoting data."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def compare(published, candidate):
    seeds = [json.loads((folder / "demo_seed.json").read_text(encoding="utf-8")) for folder in (published, candidate)]
    indexed = []
    for seed in seeds:
        records = {row["geoid"]: row for row in seed["geographies"]}
        if len(records) != len(seed["geographies"]):
            raise ValueError("Duplicate geography identifiers")
        indexed.append(records)
    left, right = indexed
    changes = []
    field_counts = Counter()
    existing_value_changes = 0
    value_changes = []
    def inspect(left, right, path):
        nonlocal existing_value_changes
        if isinstance(left, dict) and isinstance(right, dict):
            for key in left.keys() | right.keys():
                name = f"{path}.{key}"
                if key not in left:
                    field_counts[f"added:{name}"] += 1
                elif key not in right:
                    field_counts[f"removed:{name}"] += 1
                    existing_value_changes += 1
                else:
                    inspect(left[key], right[key], name)
        elif isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
            for old, new in zip(left, right):
                inspect(old, new, f"{path}[]")
        elif left != right:
            field_counts[f"changed:{path}"] += 1
            existing_value_changes += 1
            if len(value_changes) < 40:
                value_changes.append({"geoid": geoid, "field": path, "old": left, "new": right})
    for geoid in sorted(left.keys() & right.keys()):
        for key in sorted(left[geoid].keys() | right[geoid].keys()):
            if key not in left[geoid] or key not in right[geoid] or left[geoid][key] != right[geoid][key]:
                changes.append({"geoid": geoid, "field": key})
                inspect(left[geoid].get(key), right[geoid].get(key), key)
    tables = []
    for folder in (published, candidate):
        with (folder / "statcan_ct_metrics.csv").open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            tables.append((reader.fieldnames, sorted(json.dumps(row, sort_keys=True) for row in reader)))
    return {
        "published_geographies": len(left), "candidate_geographies": len(right),
        "added": sorted(right.keys() - left.keys()), "removed": sorted(left.keys() - right.keys()),
        "changed_geography_field_count": len(changes),
        "changed_geography_fields_sample": changes[:5],
        "field_change_counts": dict(sorted(field_counts.items())),
        "existing_value_changes": existing_value_changes,
        "value_change_sample": value_changes,
        "csv_equal": tables[0] == tables[1],
        "published_csv_rows": len(tables[0][1]), "candidate_csv_rows": len(tables[1][1]),
        "published_metadata": seeds[0].get("metadata"), "candidate_metadata": seeds[1].get("metadata"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--published", type=Path, default=Path("app/data"))
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.published, args.candidate), indent=2))
