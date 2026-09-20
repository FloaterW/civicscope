"""Keep observation periods separate from source checks and database loads."""
from datetime import UTC, datetime
from importlib.resources import files
from sqlalchemy import func
from app.models import CmhcMetric, ETLRun, Geography, Metric
from app.services.transit_provenance import load_transit_manifest
from app.services.refresh_provenance import verified_sources


def build_data_status(db):
    sources = verified_sources(files("app.data"))
    transit = load_transit_manifest()
    periods = {
        "census": db.query(func.max(Metric.year)).scalar(),
        "cmhc": db.query(func.max(CmhcMetric.year)).scalar(),
        "transit": None,
    }
    limits = {"census": 180, "cmhc": 45, "transit": 14}
    status = []
    for name, period in periods.items():
        checked = sources.get(name, {}).get("last_checked_at")
        age = None
        if not isinstance(checked, str):
            checked = None
        if checked:
            try:
                timestamp = datetime.fromisoformat(checked.replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    raise ValueError("Missing timezone")
                age = (datetime.now(UTC) - timestamp).total_seconds() / 86400
                if age < 0:
                    checked, age = None, None
            except (ValueError, TypeError):
                checked, age = None, None
        status.append({
            "source": name, "observation_year": period,
            "last_checked_at": checked,
            "check_status": "unknown" if age is None else "overdue" if age > limits[name] else "checked",
            "check_interval_days": limits[name],
            "packaged_at": transit.get("packaged_at") if name == "transit" else None,
            "coverage": transit.get("coverage_status", "unknown") if name == "transit" else None,
        })
    last_load = db.query(func.max(ETLRun.completed_at)).filter(ETLRun.status == "success").scalar()
    return {
        "sources": status,
        "geography_count": db.query(Geography).count(),
        "last_database_load_at": last_load.isoformat() if last_load else None,
        "note": "Source checks and database loads are not observation dates. Unknown means no matching verified refresh record is available. CMHC checks cover municipality and tract files, not the separately maintained survey-zone snapshot.",
    }
