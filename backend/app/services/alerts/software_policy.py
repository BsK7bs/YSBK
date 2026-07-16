"""Software Policy & Compliance module.

Provides:
    * The **catalog**: per-org normalized software inventory across devices
      (first_seen/last_seen, publishers, versions, category, device_count).
    * The **policy**: monitor / blocklist / allowlist modes with allow/block
      rule lists (name + publisher + version constraint).
    * The **compliance calculator**: violations, unauthorized devices,
      compliance score (0-100).
    * Rule integration: ``evaluate_software_policy_triggers`` produces
      ``RuleTrigger`` objects for the Alert Engine.

Collections used:
    * ``software_policies``: {org_id, mode, updated_at, updated_by}
    * ``software_rules``:    {id, org_id, mode: 'allow'|'block', name,
                              publisher, min_version, max_version, category,
                              severity_override, notes, created_at, created_by}
    * ``software_catalog``:  {id, org_id, key(name+publisher), name, publisher,
                              category, versions[], device_count, first_seen,
                              last_seen, license, tags}
    * ``software_device_index``: {org_id, device_id, name, publisher, version,
                                  first_seen, last_seen}

Mode semantics:
    monitor    → no violations; inventory only.
    blocklist  → anything matching a block rule is a violation.
    allowlist  → anything NOT matching an allow rule is a violation.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

log = logging.getLogger("software.policy")

CATEGORY_HINTS: dict[str, str] = {
    r"chrome|firefox|edge|safari|brave|opera": "Browser",
    r"visual\s?studio\s?code|vscode|jetbrains|pycharm|intellij|sublime|atom": "IDE",
    r"office|word|excel|powerpoint|onedrive|outlook|libreoffice": "Office",
    r"slack|zoom|teams|webex|discord": "Communication",
    r"steam|epic\s?games|origin|riot\s?client|battle\.net": "Games",
    r"7-?zip|winrar|winzip|notepad\+\+|putty|wireshark": "Utilities",
    r"symantec|mcafee|kaspersky|bitdefender|malwarebytes|avast|avg|defender": "Security",
    r"python|node|docker|git|postman|kubernetes|terraform": "Developer Tools",
}

DEFAULT_MODE = "monitor"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _key(name: str | None, publisher: str | None) -> str:
    return f"{_norm(name)}|{_norm(publisher)}"


def guess_category(name: str | None, publisher: str | None) -> str:
    hay = f"{name or ''} {publisher or ''}".lower()
    for pattern, cat in CATEGORY_HINTS.items():
        if re.search(pattern, hay):
            return cat
    return "Uncategorized"


def _extract_software_list(inventory: dict) -> list[dict]:
    """Try several shapes the agent may send."""
    if not isinstance(inventory, dict):
        return []
    for key in ("software", "applications", "installed_software", "programs"):
        val = inventory.get(key)
        if isinstance(val, list) and val:
            return [x for x in val if isinstance(x, dict)]
        if isinstance(val, dict):
            items = (val.get("items") or val.get("list")
                     or val.get("programs") or val.get("software")
                     or val.get("installed_software") or val.get("applications"))
            if isinstance(items, list):
                return [x for x in items if isinstance(x, dict)]
    return []


# ---------------------------------------------------------------------------
# Policy CRUD helpers
# ---------------------------------------------------------------------------

async def get_policy(db, org_id: str) -> dict[str, Any]:
    doc = await db.software_policies.find_one({"org_id": org_id}, {"_id": 0})
    return doc or {"org_id": org_id, "mode": DEFAULT_MODE, "updated_at": None}


async def set_policy(db, org_id: str, mode: str, actor: dict | None = None) -> dict[str, Any]:
    if mode not in ("monitor", "blocklist", "allowlist"):
        raise ValueError("invalid mode")
    doc = {
        "org_id": org_id,
        "mode": mode,
        "updated_at": _now_iso(),
        "updated_by": (actor or {}).get("email"),
    }
    await db.software_policies.update_one({"org_id": org_id}, {"$set": doc}, upsert=True)
    return doc


async def list_rules(db, org_id: str, mode: str | None = None) -> list[dict]:
    q: dict = {"org_id": org_id}
    if mode:
        q["mode"] = mode
    return await db.software_rules.find(q, {"_id": 0}).to_list(1000)


async def add_rule(db, org_id: str, payload: dict, actor: dict | None = None) -> dict:
    doc = {
        "id": str(uuid.uuid4()),
        "org_id": org_id,
        "mode": payload.get("mode") or "block",
        "name": payload.get("name") or "",
        "publisher": payload.get("publisher") or "",
        "min_version": payload.get("min_version") or None,
        "max_version": payload.get("max_version") or None,
        "category": payload.get("category") or guess_category(payload.get("name"), payload.get("publisher")),
        "severity_override": payload.get("severity_override") or None,
        "notes": payload.get("notes") or "",
        "created_at": _now_iso(),
        "created_by": (actor or {}).get("email"),
    }
    if doc["mode"] not in ("allow", "block"):
        raise ValueError("rule mode must be 'allow' or 'block'")
    result = await db.software_rules.insert_one(doc)
    # Remove MongoDB's _id before returning
    doc.pop("_id", None)
    return doc


async def delete_rule(db, org_id: str, rule_id: str) -> bool:
    res = await db.software_rules.delete_one({"id": rule_id, "org_id": org_id})
    return res.deleted_count > 0


async def bulk_add_rules(db, org_id: str, entries: Iterable[dict], mode: str,
                        actor: dict | None = None) -> int:
    docs = []
    for e in entries:
        if not e or not (e.get("name") or e.get("publisher")):
            continue
        docs.append({
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "mode": mode,
            "name": e.get("name") or "",
            "publisher": e.get("publisher") or "",
            "min_version": e.get("min_version") or None,
            "max_version": e.get("max_version") or None,
            "category": e.get("category") or guess_category(e.get("name"), e.get("publisher")),
            "severity_override": e.get("severity_override") or None,
            "notes": e.get("notes") or "",
            "created_at": _now_iso(),
            "created_by": (actor or {}).get("email"),
        })
    if not docs:
        return 0
    await db.software_rules.insert_many(docs)
    return len(docs)


# ---------------------------------------------------------------------------
# Inventory ingest: keep catalog + device index up-to-date
# ---------------------------------------------------------------------------

async def upsert_catalog_from_device(db, org_id: str, device_id: str,
                                     inventory: dict) -> list[dict]:
    """Given a device's inventory, refresh the org catalog + device index.

    Also detects **new**, **removed** and **outdated** software vs the
    previous snapshot for this device, and writes those into the
    ``software_events`` collection so admins can browse the change log
    without polling the full inventory.

    Returns the normalized list of software entries recorded.
    """
    items = _extract_software_list(inventory)
    now = _now_iso()

    # ------------------------------------------------------------------
    # 0) Diff against the previous snapshot (before we wipe it).
    # ------------------------------------------------------------------
    prev_docs = await db.software_device_index.find(
        {"org_id": org_id, "device_id": device_id},
        {"_id": 0, "key": 1, "name": 1, "publisher": 1, "version": 1},
    ).to_list(20000)
    prev_by_key = {d["key"]: d for d in prev_docs}

    normalized: list[dict] = []
    curr_by_key: dict[str, dict] = {}
    for it in items:
        name = str(it.get("name") or it.get("display_name") or it.get("DisplayName") or "").strip()
        publisher = str(it.get("publisher") or it.get("Publisher") or it.get("vendor") or "").strip()
        version = str(it.get("version") or it.get("Version") or "").strip()
        install_date = str(it.get("install_date") or it.get("InstallDate") or "").strip()
        if not name:
            continue
        key = _key(name, publisher)
        entry = {
            "org_id": org_id,
            "device_id": device_id,
            "name": name,
            "publisher": publisher,
            "version": version,
            "install_date": install_date or None,
            "key": key,
            "first_seen": (prev_by_key.get(key) or {}).get("first_seen") or now,
            "last_seen": now,
        }
        curr_by_key[key] = entry
        normalized.append(entry)

    # ------------------------------------------------------------------
    # 1) Emit software_events for the diff.
    # ------------------------------------------------------------------
    events: list[dict] = []
    new_keys = curr_by_key.keys() - prev_by_key.keys()
    removed_keys = prev_by_key.keys() - curr_by_key.keys()
    version_changed = [
        k for k in (curr_by_key.keys() & prev_by_key.keys())
        if _norm(curr_by_key[k].get("version", "")) != _norm(prev_by_key[k].get("version", ""))
    ]
    for k in new_keys:
        e = curr_by_key[k]
        events.append({
            "id": str(uuid.uuid4()), "org_id": org_id, "device_id": device_id, "ts": now,
            "kind": "new", "name": e["name"], "publisher": e["publisher"],
            "version": e["version"], "install_date": e.get("install_date"),
        })
    for k in removed_keys:
        e = prev_by_key[k]
        events.append({
            "id": str(uuid.uuid4()), "org_id": org_id, "device_id": device_id, "ts": now,
            "kind": "removed", "name": e.get("name"), "publisher": e.get("publisher"),
            "version": e.get("version"),
        })
    for k in version_changed:
        cur = curr_by_key[k]; prv = prev_by_key[k]
        events.append({
            "id": str(uuid.uuid4()), "org_id": org_id, "device_id": device_id, "ts": now,
            "kind": "version_changed", "name": cur["name"], "publisher": cur["publisher"],
            "old_version": prv.get("version"), "version": cur.get("version"),
        })
    if events:
        await db.software_events.insert_many(events)
        log.info("[software-diff] device=%s org=%s new=%d removed=%d ver_changed=%d",
                 device_id, org_id, len(new_keys), len(removed_keys), len(version_changed))

    # ------------------------------------------------------------------
    # 2) Reset the device index for this device, then insert fresh entries.
    # ------------------------------------------------------------------
    await db.software_device_index.delete_many({"org_id": org_id, "device_id": device_id})
    if normalized:
        await db.software_device_index.insert_many([dict(e) for e in normalized])

    # ------------------------------------------------------------------
    # 3) Refresh catalog: for each unique (name, publisher), update aggregate.
    # ------------------------------------------------------------------
    catalog_updates: dict[str, dict] = {}
    for e in normalized:
        k = e["key"]
        c = catalog_updates.setdefault(k, {
            "name": e["name"], "publisher": e["publisher"],
            "versions": set(),
        })
        if e["version"]:
            c["versions"].add(e["version"])

    for k, c in catalog_updates.items():
        existing = await db.software_catalog.find_one({"org_id": org_id, "key": k}, {"_id": 0})
        # Recompute device_count fresh.
        device_count = await db.software_device_index.count_documents({"org_id": org_id, "key": k})
        merged_versions = set(c["versions"]) | set((existing or {}).get("versions") or [])
        # Compute how many devices are BEHIND `latest_known_version` (if set).
        latest = (existing or {}).get("latest_known_version") or ""
        outdated_count = 0
        if latest:
            outdated_count = await db.software_device_index.count_documents({
                "org_id": org_id, "key": k,
                "version": {"$nin": ["", latest]},
            })
        doc = {
            "org_id": org_id,
            "key": k,
            "name": c["name"],
            "publisher": c["publisher"],
            "category": (existing or {}).get("category") or guess_category(c["name"], c["publisher"]),
            "versions": sorted(merged_versions),
            "device_count": device_count,
            "outdated_count": outdated_count,
            "latest_known_version": latest or None,
            "first_seen": (existing or {}).get("first_seen") or now,
            "last_seen": now,
            "license": (existing or {}).get("license"),
        }
        if not existing:
            doc["id"] = str(uuid.uuid4())
        await db.software_catalog.update_one(
            {"org_id": org_id, "key": k}, {"$set": doc}, upsert=True
        )

    # ------------------------------------------------------------------
    # 4) Recompute device_count for catalog items no longer present on this device.
    #    (Cheap: iterate all catalog docs; small orgs.)
    # ------------------------------------------------------------------
    async for c in db.software_catalog.find({"org_id": org_id}, {"_id": 0, "key": 1}):
        n = await db.software_device_index.count_documents({"org_id": org_id, "key": c["key"]})
        await db.software_catalog.update_one({"org_id": org_id, "key": c["key"]},
                                             {"$set": {"device_count": n}})
    return normalized


# ---------------------------------------------------------------------------
# Matching + violation detection
# ---------------------------------------------------------------------------

def _matches_rule(entry: dict, rule: dict) -> bool:
    if rule.get("name") and _norm(rule["name"]) not in _norm(entry.get("name")):
        return False
    if rule.get("publisher") and _norm(rule["publisher"]) not in _norm(entry.get("publisher")):
        return False
    # (version constraints intentionally simple; expand later.)
    if rule.get("min_version") and entry.get("version"):
        if entry["version"] < rule["min_version"]:
            return False
    if rule.get("max_version") and entry.get("version"):
        if entry["version"] > rule["max_version"]:
            return False
    return True


async def find_violations(db, org_id: str, entries: list[dict]) -> list[dict]:
    policy = await get_policy(db, org_id)
    mode = policy.get("mode") or DEFAULT_MODE
    if mode == "monitor":
        return []
    block_rules = await list_rules(db, org_id, "block") if mode == "blocklist" else []
    allow_rules = await list_rules(db, org_id, "allow") if mode == "allowlist" else []
    violations: list[dict] = []
    for e in entries:
        if mode == "blocklist":
            for r in block_rules:
                if _matches_rule(e, r):
                    violations.append({"entry": e, "rule": r,
                                       "policy_violated": "Blocklist",
                                       "reason": f"Matches block rule for '{r.get('name') or r.get('publisher')}'."})
                    break
        elif mode == "allowlist":
            allowed = any(_matches_rule(e, r) for r in allow_rules)
            if not allowed:
                violations.append({"entry": e, "rule": None,
                                   "policy_violated": "Allowlist",
                                   "reason": "Software is not on the approved allowlist."})
    return violations


# ---------------------------------------------------------------------------
# Trigger emission for the Alert Engine
# ---------------------------------------------------------------------------

async def evaluate_software_policy_triggers(db, org_id: str, inventory: dict,
                                             device: dict) -> list:
    """Emit one ``RuleTrigger`` per software violation on this device.

    Also emits a *clear* signal for any active alert whose software is no
    longer present on the device.
    """
    from .rules import RuleTrigger  # local import avoids circulars

    entries = _extract_software_list(inventory)
    normalized: list[dict] = []
    for it in entries:
        name = str(it.get("name") or it.get("display_name") or it.get("DisplayName") or "").strip()
        if not name:
            continue
        normalized.append({
            "name": name,
            "publisher": str(it.get("publisher") or it.get("Publisher") or it.get("vendor") or "").strip(),
            "version": str(it.get("version") or it.get("Version") or "").strip(),
        })
    violations = await find_violations(db, org_id, normalized)
    triggers = []
    active_dimensions: set[str] = set()
    for v in violations:
        e = v["entry"]
        dim = _key(e["name"], e.get("publisher"))
        active_dimensions.add(dim)
        sev = (v.get("rule") or {}).get("severity_override") or "high"
        triggers.append(RuleTrigger(
            rule_key="software.policy",
            title="Software policy violation",
            category="compliance",
            triggered=True,
            severity=sev,
            current_value=e["name"] + (f" {e['version']}" if e.get("version") else ""),
            unit="software",
            dimension_key=dim,
            recommendation="Review the software policy and remove or approve the software.",
            context={
                "software_name": e["name"],
                "publisher": e.get("publisher"),
                "version": e.get("version"),
                "policy_violated": v["policy_violated"],
                "reason": v["reason"],
                "recommended_action": "Uninstall the software or add an allow rule if approved.",
            },
        ))

    # Clear-signal: for any active software.policy alert on this device whose
    # dimension is no longer in violations, mark clear.
    async for existing in db.alerts.find({
        "org_id": org_id,
        "device_id": device["id"],
        "rule_key": "software.policy",
        "status": {"$in": ["open", "resolved_awaiting_ack"]},
    }, {"_id": 0, "dimension_key": 1}):
        dim = existing.get("dimension_key") or ""
        if dim and dim not in active_dimensions:
            triggers.append(RuleTrigger(
                rule_key="software.policy",
                title="Software policy violation",
                category="compliance",
                clear=True,
                dimension_key=dim,
            ))
    return triggers


# ---------------------------------------------------------------------------
# Compliance score + dashboard metrics
# ---------------------------------------------------------------------------

async def compliance_summary(db, org_id: str) -> dict[str, Any]:
    policy = await get_policy(db, org_id)
    mode = policy.get("mode") or DEFAULT_MODE
    total_devices = await db.devices.count_documents({"org_id": org_id})
    active_violations = await db.alerts.count_documents({
        "org_id": org_id, "rule_key": "software.policy",
        "status": {"$in": ["open", "resolved_awaiting_ack"]},
    })
    violating_devices = 0
    if active_violations:
        violating_devices = len(await db.alerts.distinct("device_id", {
            "org_id": org_id, "rule_key": "software.policy",
            "status": {"$in": ["open", "resolved_awaiting_ack"]},
        }))

    catalog_total = await db.software_catalog.count_documents({"org_id": org_id})
    if mode == "monitor":
        compliance = 100
    elif total_devices == 0:
        compliance = 100
    else:
        compliant = max(0, total_devices - violating_devices)
        compliance = int(round(100.0 * compliant / total_devices))

    # Top installed
    top_installed = await db.software_catalog.find(
        {"org_id": org_id}, {"_id": 0, "name": 1, "publisher": 1, "device_count": 1, "category": 1}
    ).sort("device_count", -1).limit(10).to_list(10)

    # Recently detected (by last_seen)
    recent = await db.software_catalog.find(
        {"org_id": org_id}, {"_id": 0, "name": 1, "publisher": 1, "first_seen": 1, "category": 1}
    ).sort("first_seen", -1).limit(10).to_list(10)

    return {
        "policy_mode": mode,
        "compliance_score": compliance,
        "total_devices": total_devices,
        "violating_devices": violating_devices,
        "active_violations": active_violations,
        "catalog_total": catalog_total,
        "top_installed": top_installed,
        "recently_detected": recent,
    }


async def list_inventory(db, org_id: str, *, q: str | None = None,
                        category: str | None = None,
                        limit: int = 100) -> list[dict]:
    query: dict = {"org_id": org_id}
    if category:
        query["category"] = category
    if q:
        query["$or"] = [
            {"name": {"$regex": re.escape(q), "$options": "i"}},
            {"publisher": {"$regex": re.escape(q), "$options": "i"}},
        ]
    return await db.software_catalog.find(query, {"_id": 0}).sort("device_count", -1).limit(limit).to_list(limit)
