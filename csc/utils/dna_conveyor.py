import hashlib
import json
import os
import tempfile
import zipfile
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "canonicalize_json",
    "spec_seed_fingerprint",
    "unpack_bundle",
    "repack_with_artifacts",
]

def canonicalize_json(obj: Any) -> str:
    """
    Deterministic JSON representation: UTF-8, sorted keys, no whitespace variance.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8").decode("utf-8")


def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def spec_seed_fingerprint(
    spec: Dict[str, Any],
    seed: Optional[Dict[str, Any]],
    engine_version: str,
    csc_version: str,
) -> str:
    """
    Fingerprint for run_id:
    sha256(canonical(spec) + "|" + canonical(seed or {}) + "|" + engine_version + "|" + csc_version)
    """
    spec_s = canonicalize_json(spec)
    seed_s = canonicalize_json(seed or {})
    payload = (spec_s + "|" + seed_s + "|" + str(engine_version) + "|" + str(csc_version)).encode("utf-8")
    return _sha256_bytes(payload)


def unpack_bundle(bundle_path: str, workdir: Optional[str] = None) -> Tuple[str, bool]:
    """
    If bundle_path is a .zip → extract to temp dir and return (root_dir, True).
    If bundle_path is a file path to spec.json → return (dir_of_spec, False).
    If bundle_path is a directory → return it (pass-through), False.

    Caller is responsible for cleaning up temp dir if is_zip is True.
    """
    if os.path.isdir(bundle_path):
        return bundle_path, False

    lower = bundle_path.lower()
    if lower.endswith(".zip"):
        td = tempfile.mkdtemp(prefix="csc_zip_") if workdir is None else workdir
        with zipfile.ZipFile(bundle_path, "r") as zf:
            zf.extractall(td)
        return td, True

    # treat as file path (e.g., .../spec.json)
    return os.path.dirname(os.path.abspath(bundle_path)), False


def _iter_zip(src_zip_path: str):
    with zipfile.ZipFile(src_zip_path, "r") as zf:
        for info in zf.infolist():
            with zf.open(info.filename, "r") as fh:
                yield info, fh.read()


def repack_with_artifacts(
    input_path: str,
    artifacts_dir: str,
    output_zip_path: str,
    artifacts_prefix: str = "artifacts/",
) -> None:
    """
    Repack preserving all original contents (byte-for-byte) and add CSC artifacts
    under `artifacts_prefix`. If input_path is a .zip we *copy* its entries. If it
    is a directory, we zip that directory.

    Unknown payloads are preserved exactly; we do not overwrite non-artifact paths.
    """
    # Build a map for artifact files to write
    artifact_entries = []
    for root, _, files in os.walk(artifacts_dir):
        for fn in files:
            abs_path = os.path.join(root, fn)
            rel = os.path.relpath(abs_path, artifacts_dir).replace("\\", "/")
            artifact_entries.append((abs_path, artifacts_prefix + rel))

    if os.path.isdir(input_path):
        # Zip directory contents + artifacts
        with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for root, _, files in os.walk(input_path):
                for fn in files:
                    abs_path = os.path.join(root, fn)
                    rel = os.path.relpath(abs_path, input_path).replace("\\", "/")
                    # Skip if we would collide under artifacts_prefix (we never write non-artifact collisions)
                    if rel.startswith(artifacts_prefix):
                        continue
                    zout.write(abs_path, arcname=rel)
            # Now add artifacts
            for abs_path, arcname in artifact_entries:
                zout.write(abs_path, arcname=arcname)
        return

    if input_path.lower().endswith(".zip"):
        with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            # Copy original entries verbatim
            for info, data in _iter_zip(input_path):
                # Avoid accidental overwrite into artifacts/ by skipping any existing artifacts path
                if info.filename.startswith(artifacts_prefix):
                    continue
                zi = zipfile.ZipInfo(info.filename)
                zi.date_time = info.date_time
                zi.compress_type = info.compress_type
                zi.external_attr = info.external_attr
                zi.comment = info.comment
                zi.extra = info.extra
                zi.internal_attr = info.internal_attr
                zi.flag_bits = info.flag_bits
                zi.create_system = info.create_system
                zout.writestr(zi, data)
            # Write artifacts
            for abs_path, arcname in artifact_entries:
                zout.write(abs_path, arcname=arcname)
        return

    # Fallback: treat as single file (e.g., spec.json) — create a minimal base zip plus artifacts
    base_dir = os.path.dirname(os.path.abspath(input_path))
    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for root, _, files in os.walk(base_dir):
            for fn in files:
                abs_path = os.path.join(root, fn)
                rel = os.path.relpath(abs_path, base_dir).replace("\\", "/")
                if rel.startswith(artifacts_prefix):
                    continue
                zout.write(abs_path, arcname=rel)
        for abs_path, arcname in artifact_entries:
            zout.write(abs_path, arcname=arcname)
