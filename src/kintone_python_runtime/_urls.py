from __future__ import annotations

from urllib.parse import urljoin


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def guest_space_path_fragment(guest_space_id: str | int) -> str:
    return str(guest_space_id).strip()


def api_path(path: str, *, guest_space_id: str | int | None) -> str:
    """
    Build API path with optional guest space prefix.

    Normal: /k/v1/records -> /k/v1/records.json
    Guest: /k/v1/records -> /k/guest/{id}/v1/records.json
    """
    p = path if path.endswith(".json") else f"{path}.json"
    if guest_space_id is None:
        return p if p.startswith("/") else f"/{p}"
    g = guest_space_path_fragment(guest_space_id)
    if p.startswith("/k/"):
        rest = p.removeprefix("/k/").lstrip("/")
        return f"/k/guest/{g}/{rest}"
    msg = f"path must start with /k/ for guest space, got {path!r}"
    raise ValueError(msg)


def join_base_url(base_url: str, path: str) -> str:
    base = normalize_base_url(base_url) + "/"
    rel = path.lstrip("/")
    return urljoin(base, rel)
