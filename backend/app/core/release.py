"""Public release identity: only a full Git SHA, never arbitrary environment text."""
import os
import re


def release_commit() -> str | None:
    # The hosting provider is authoritative; a stale manual override must not
    # disguise a different deployed revision. The fallback supports local builds.
    raw = os.getenv("RENDER_GIT_COMMIT", os.getenv("CIVICSCOPE_BUILD_SHA", ""))
    return raw.lower() if re.fullmatch(r"[0-9a-fA-F]{40}", raw) else None
