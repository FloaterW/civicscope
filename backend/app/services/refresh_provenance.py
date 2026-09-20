"""Validate source check evidence against immutable packaged artifacts."""
import hashlib
import json
from functools import lru_cache

ARTIFACTS = {
    "census": ("demo_seed.json", "statcan_ct_metrics.csv"),
    "cmhc": ("cmhc_seed.json", "cmhc_ct_metrics.csv"),
    "transit": ("transit_scores.csv", "transit_routes.geojson", "transit_manifest.json"),
}


def packaged_digest(path):
    # Git checks these text artifacts out as LF in deployment. Normalize Windows
    # working copies too, so evidence is portable without changing data values.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@lru_cache(maxsize=1)
def verified_sources(directory):
    # Packaged files are immutable for a process lifetime. Hash once, not on
    # every health check (the geography seed is large).
    try:
        manifest = json.loads(directory.joinpath("refresh_manifest.json").read_text(encoding="utf-8"))
        sources = manifest["sources"]
        if not isinstance(sources, dict):
            return {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    verified = {}
    for source, names in ARTIFACTS.items():
        try:
            evidence = sources[source]
            if all(
                packaged_digest(directory.joinpath(name))
                == evidence["artifacts"][name]["sha256"]
                for name in names
            ):
                verified[source] = evidence
        except (OSError, KeyError, TypeError):
            continue
    return verified
