from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def _require_object(value: Any, *, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(message)
    return dict(value)


def _require_non_empty_str(value: Any, *, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(message)
    return value.strip()


def _as_string_list(value: Any, *, field: str) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    raise ValueError(f"selection.{field} must be string or list[str]")


def _selection_bool(selection: Mapping[str, Any], key: str, *, default: bool = False) -> bool:
    value = selection.get(key, default)
    if isinstance(value, bool):
        return value
    raise ValueError(f"selection.{key} must be a boolean")


def _selection_require_capabilities(selection: Mapping[str, Any]) -> list[str]:
    value = selection.get("require_capabilities")
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ValueError("selection.require_capabilities must be list[str]")
    return list(value)


def _selection_order_by(selection: Mapping[str, Any]) -> str:
    value = selection.get("order_by", "run_key_asc")
    if not isinstance(value, str):
        raise ValueError("selection.order_by must be a string")
    if value not in {"run_key_asc", "created_at_desc", "created_at_asc"}:
        raise ValueError(
            "selection.order_by must be one of: run_key_asc, created_at_desc, created_at_asc"
        )
    return value


def _parse_run_status(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _sort_selected_rows(rows: list[dict[str, Any]], *, order_by: str) -> list[dict[str, Any]]:
    if order_by == "run_key_asc":
        return sorted(rows, key=lambda row: row["run_key"])
    if order_by == "created_at_asc":
        return sorted(
            rows,
            key=lambda row: (
                row["created_at"] is None,
                row["created_at"] or "",
                row["run_key"],
            ),
        )
    assert order_by == "created_at_desc"
    with_created = [row for row in rows if row["created_at"] is not None]
    with_created.sort(key=lambda row: ((row["created_at"] or ""), row["run_key"]), reverse=True)
    without_created = sorted(
        [row for row in rows if row["created_at"] is None],
        key=lambda row: row["run_key"],
    )
    return with_created + without_created


def _dedupe_by_run_id(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        run_id = row.get("run_id")
        dedupe_key = run_id if isinstance(run_id, str) and run_id else row["run_key"]
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(row)
    return deduped


def _dataset_payload(payload: Any) -> dict[str, Any]:
    data = _require_object(payload, message="dataset entry must be an object")
    name = _require_non_empty_str(data.get("name"), message="dataset missing name")
    query = data.get("query")
    generator = data.get("generator")
    fmt = data.get("format", "jsonl")
    file = data.get("file")

    if generator is not None:
        generator = _require_non_empty_str(
            generator, message=f"dataset {name!r} has invalid generator"
        )
    if query is not None:
        query = _require_non_empty_str(query, message=f"dataset {name!r} has invalid query")
    if (query is None) == (generator is None):
        raise ValueError(f"dataset {name!r} must set exactly one of query or generator")
    if fmt not in {"jsonl", "parquet", "dir"}:
        raise ValueError(f"dataset {name!r} has invalid format: {fmt!r}")
    if file is not None and (not isinstance(file, str) or not file.strip()):
        raise ValueError(f"dataset {name!r} has invalid file")
    if isinstance(file, str) and ("/" in file or "\\" in file):
        raise ValueError(f"dataset {name!r} file must be a base name, got: {file!r}")

    return {
        "name": name,
        "query": query if isinstance(query, str) else None,
        "generator": generator if isinstance(generator, str) else None,
        "format": fmt,
        "file": file,
    }

def load_job_config(path: Path) -> dict[str, Any]:
    data = _require_object(json.loads(path.read_text()), message="job config must be a JSON object")
    if data.get("schema_version") != 2:
        raise ValueError("job config schema_version must be 2")

    datasets_raw = data.get("datasets")
    if not isinstance(datasets_raw, list) or not datasets_raw:
        raise ValueError("job config datasets must be a non-empty list")
    reference = data.get("reference")
    if reference is not None:
        reference = _require_object(reference, message="job config reference must be an object")
        if "build_outcomes" in reference:
            ref_sel = reference.get("selection")
            if not isinstance(ref_sel, dict) or not ref_sel:
                raise ValueError(
                    "reference.selection must be a non-empty object "
                    "when reference.build_outcomes is set"
                )

    return {
        "schema_version": 2,
        "name": _require_non_empty_str(data.get("name"), message="job config missing name"),
        "selection": _require_object(
            data.get("selection", {}),
            message="job config selection must be an object",
        ),
        "reference": reference,
        "datasets": [_dataset_payload(ds) for ds in datasets_raw],
    }


def build_selected_runs_query(*, selection: Mapping[str, Any]) -> tuple[str, list[Any]]:
    where: list[str] = []
    params: list[Any] = []

    rid = selection.get("root_id")
    if rid is not None:
        rid = _require_non_empty_str(rid, message="selection.root_id must be a string")
        where.append("root_id = ?")
        params.append(rid)

    run_dir_prefix = selection.get("run_dir_prefix")
    if run_dir_prefix is not None:
        run_dir_prefix = _require_non_empty_str(
            run_dir_prefix, message="selection.run_dir_prefix must be a string"
        )
        where.append("(run_dir = ? OR run_dir LIKE ?)")
        params.extend([run_dir_prefix, run_dir_prefix + "/%"])

    def _in(field: str, values: Any) -> None:
        if values is None:
            return
        vals = _as_string_list(values, field=field)
        if not vals:
            return
        where.append(field + " IN (" + ",".join("?" for _ in vals) + ")")
        params.extend(vals)

    for field in (
        "run_dir",
        "provider",
        "backend",
        "mode",
        "corpus",
        "goal_sig_scheme",
        "config_whitelist_hash",
        "config_full_hash",
        "rel_run_dir",
    ):
        _in(field, selection.get(field))

    clause = " AND ".join(where) if where else "TRUE"
    query = (
        "SELECT run_key, root_id, rel_run_dir, run_dir, run_id, created_at, run_status "
        f"FROM runs WHERE {clause} ORDER BY run_key"
    )
    return query, params


def create_selected_runs_view(
    conn: Any, *, selection: Mapping[str, Any]
) -> dict[str, Any]:
    query, params = build_selected_runs_query(selection=selection)
    raw_rows = conn.execute(query, params).fetchall()
    resolved_rows: list[dict[str, Any]] = []
    for row in raw_rows:
        run_key, root_id, rel_run_dir, run_dir, run_id, created_at, run_status_raw = row
        if not (
            isinstance(run_key, str)
            and run_key
            and isinstance(root_id, str)
            and root_id
            and isinstance(rel_run_dir, str)
            and rel_run_dir
            and isinstance(run_dir, str)
            and run_dir
        ):
            continue
        resolved_rows.append(
            {
                "run_key": run_key,
                "root_id": root_id,
                "rel_run_dir": rel_run_dir,
                "run_dir": run_dir,
                "run_id": run_id if isinstance(run_id, str) else None,
                "created_at": created_at if isinstance(created_at, str) else None,
                "run_status": _parse_run_status(run_status_raw),
            }
        )

    require_completed = _selection_bool(selection, "require_completed", default=False)
    exclude_partial = _selection_bool(selection, "exclude_partial_results", default=False)
    dedupe_run_id = _selection_bool(selection, "dedupe_run_id", default=False)
    require_capabilities = _selection_require_capabilities(selection)
    order_by = _selection_order_by(selection)
    max_runs = selection.get("max_runs")
    if max_runs is not None and (not isinstance(max_runs, int) or max_runs <= 0):
        raise ValueError("selection.max_runs must be an integer > 0")

    filtered_rows: list[dict[str, Any]] = []
    for row in resolved_rows:
        status_payload = row["run_status"]
        status = None
        partial_results = None
        capabilities: dict[str, Any] | None = None
        if isinstance(status_payload, dict):
            raw_status = status_payload.get("status")
            if isinstance(raw_status, str):
                status = raw_status
            raw_partial = status_payload.get("partial_results")
            if isinstance(raw_partial, bool):
                partial_results = raw_partial
            raw_capabilities = status_payload.get("capabilities")
            if isinstance(raw_capabilities, dict):
                capabilities = raw_capabilities

        if require_completed and status != "completed":
            continue
        if exclude_partial and partial_results is True:
            continue
        if require_capabilities:
            if not isinstance(capabilities, dict):
                continue
            missing = [key for key in require_capabilities if capabilities.get(key) is not True]
            if missing:
                continue
        filtered_rows.append(row)

    ordered_rows = _sort_selected_rows(filtered_rows, order_by=order_by)
    if dedupe_run_id:
        ordered_rows = _dedupe_by_run_id(ordered_rows)
    if max_runs is not None:
        ordered_rows = ordered_rows[:max_runs]

    rows = [
        (row["run_key"], row["root_id"], row["rel_run_dir"], row["run_dir"])
        for row in ordered_rows
    ]
    run_keys = [row[0] for row in rows]
    conn.execute("DROP TABLE IF EXISTS selected_runs")
    conn.execute("CREATE TEMP TABLE selected_runs(run_key VARCHAR)")
    if run_keys:
        conn.executemany("INSERT INTO selected_runs VALUES (?)", [(rk,) for rk in run_keys])
    return {
        "count": len(run_keys),
        "run_keys": run_keys,
        "rows": rows,
        "selection_stats": {
            "raw_rows": len(raw_rows),
            "resolved_rows": len(resolved_rows),
            "filtered_rows": len(filtered_rows),
            "selected_rows": len(run_keys),
            "require_completed": require_completed,
            "exclude_partial_results": exclude_partial,
            "require_capabilities": require_capabilities,
            "order_by": order_by,
            "dedupe_run_id": dedupe_run_id,
            "max_runs": max_runs,
        },
    }


def resolve_same_method_as_selection(
    conn: Any, *, selection: dict[str, Any]
) -> dict[str, Any] | None:
    same = selection.get("same_method_as")
    if same is None:
        return None
    if not isinstance(same, dict):
        raise ValueError("selection.same_method_as must be an object")

    run_key = same.get("run_key")
    run_id = same.get("run_id")
    if isinstance(run_key, str) and run_key.strip():
        row = conn.execute(
            "SELECT run_key, run_id, provider, backend, rel_run_dir, run_dir, config_whitelist_hash "
            "FROM runs WHERE run_key = ?",
            [run_key.strip()],
        ).fetchone()
        if row is None:
            raise ValueError(f"selection.same_method_as.run_key not found: {run_key!r}")
        anchor_run_key, anchor_run_id, provider, backend, rel_run_dir, run_dir, method_hash = row
    elif isinstance(run_id, str) and run_id.strip():
        root_id = selection.get("root_id")
        run_dir_prefix = selection.get("run_dir_prefix")
        params: list[Any] = [run_id.strip()]
        clause = "run_id = ?"
        if isinstance(root_id, str) and root_id.strip():
            clause += " AND root_id = ?"
            params.append(root_id.strip())
        if isinstance(run_dir_prefix, str) and run_dir_prefix.strip():
            clause += " AND (run_dir = ? OR run_dir LIKE ?)"
            prefix = run_dir_prefix.strip()
            params.extend([prefix, prefix + "/%"])
        rows = conn.execute(
            "SELECT run_key, run_id, provider, backend, rel_run_dir, run_dir, config_whitelist_hash "
            f"FROM runs WHERE {clause} ORDER BY run_key",
            params,
        ).fetchall()
        if not rows:
            raise ValueError(f"selection.same_method_as.run_id not found: {run_id!r}")
        if len(rows) > 1:
            lines = [f"Ambiguous run_id {run_id!r}; candidates:"]
            for rk, rid, prov, be, rel, rd, mh in rows[:12]:
                lines.append(
                    f"  run_key={rk} provider={prov} backend={be} rel={rel} run_dir={rd} method={mh}"
                )
            if len(rows) > 12:
                lines.append(f"  ... ({len(rows) - 12} more)")
            raise ValueError("\n".join(lines))
        anchor_run_key, anchor_run_id, provider, backend, rel_run_dir, run_dir, method_hash = rows[0]
    else:
        raise ValueError("selection.same_method_as must set run_key or run_id")

    if not isinstance(method_hash, str) or not method_hash:
        raise ValueError(
            "Anchor run has no config_whitelist_hash (did you re-run `wonton.py lake reconcile`?)"
        )

    selection["config_whitelist_hash"] = method_hash
    return {
        "anchor_run_key": anchor_run_key,
        "anchor_run_id": anchor_run_id,
        "anchor_provider": provider,
        "anchor_backend": backend,
        "anchor_rel_run_dir": rel_run_dir,
        "anchor_run_dir": run_dir,
        "config_whitelist_hash": method_hash,
    }
