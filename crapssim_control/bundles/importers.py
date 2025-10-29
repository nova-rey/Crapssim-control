from __future__ import annotations

import json
import zipfile
import hashlib
from typing import Tuple, Dict, Any

from .errors import BundleReadError, SchemaMismatchError

# CSC keeps schema truths centrally; controller re-exports in many repos, but we read canonical values if available.
try:
    from crapssim_control.schemas import JOURNAL_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION  # canonical
except Exception:
    # Fallback if canonical module name differs in this repo
    JOURNAL_SCHEMA_VERSION = "1.1"
    SUMMARY_SCHEMA_VERSION = "1.1"

_EVO_STRIP_KEYS = {
    "lineage_id",
    "trial_cohort",
    "fitness_score",
    "ef",
    "cq",
    "grace_remaining",
    "origin",
    "evo_note",
    "species",
    "gen",
    "seed_note",
}


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _read_member(z: zipfile.ZipFile, name: str) -> bytes | None:
    try:
        with z.open(name, "r") as f:
            return f.read()
    except KeyError:
        return None


def _json_or_none(z: zipfile.ZipFile, name: str) -> Dict[str, Any] | None:
    raw = _read_member(z, name)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise BundleReadError(f"{name} is not valid JSON: {e}") from e


def _normalize_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(spec, dict):
        raise BundleReadError("spec.json must be a JSON object")
    clean = {k: v for k, v in spec.items() if k not in _EVO_STRIP_KEYS}
    # Back-compat key normalization examples (no-ops if keys absent)
    mapping = {
        "odds_working_on_comeout": "working_on_comeout",
    }
    for old, new in mapping.items():
        if old in clean and new not in clean:
            clean[new] = clean.pop(old)
    return clean


def _verify_schemas(manifest: Dict[str, Any] | None, report: Dict[str, Any] | None) -> None:
    if not manifest and not report:
        return
    want_j = JOURNAL_SCHEMA_VERSION
    want_s = SUMMARY_SCHEMA_VERSION
    got_j = None
    got_s = None
    # Try common locations
    for obj in (manifest, report):
        if not obj:
            continue
        got_j = got_j or obj.get("journal_schema_version") or obj.get("journalSchemaVersion")
        got_s = got_s or obj.get("summary_schema_version") or obj.get("summarySchemaVersion")
    if got_j and str(got_j) != str(want_j):
        raise SchemaMismatchError(
            f"journal_schema_version mismatch: bundle={got_j} expected={want_j}"
        )
    if got_s and str(got_s) != str(want_s):
        raise SchemaMismatchError(
            f"summary_schema_version mismatch: bundle={got_s} expected={want_s}"
        )


def import_evo_bundle(zip_path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Read an Evo bundle (.zip) and return (spec_dict, meta_dict).
    - spec_dict: normalized for CSC consumption
    - meta_dict: provenance info (source, bundle_hash, present_files, manifest/report fields if available)
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            all_names = set(z.namelist())
            raw_spec = _read_member(z, "spec.json")
            if raw_spec is None:
                raise BundleReadError("spec.json missing in bundle")
            spec = json.loads(raw_spec.decode("utf-8"))
            spec = _normalize_spec(spec)
            manifest = _json_or_none(z, "manifest.json")
            report = _json_or_none(z, "report.json")
            _verify_schemas(manifest, report)

            meta: Dict[str, Any] = {
                "source": "evo_zip",
                "present": sorted(list(all_names)),
                "bundle_hash": _hash_bytes(
                    b"".join(sorted(_read_member(z, n) or b"" for n in sorted(all_names)))
                ),
                "manifest_fields": (
                    sorted(list(manifest.keys())) if isinstance(manifest, dict) else []
                ),
                "report_fields": sorted(list(report.keys())) if isinstance(report, dict) else [],
            }
            return spec, meta
    except SchemaMismatchError:
        raise
    except BundleReadError:
        raise
    except Exception as e:
        raise BundleReadError(f"failed to read bundle: {e}") from e
