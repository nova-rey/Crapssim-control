import json
import os
import zipfile
from pathlib import Path

from csc.batch_runner import run_batch, run_single_bundle_or_spec
from csc.utils.dna_conveyor import canonicalize_json, spec_seed_fingerprint


def _write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def _make_spec(tmpdir, name="spec.json", bankroll=1000):
    spec = {"name": "demo", "bankroll": bankroll}
    p = os.path.join(tmpdir, name)
    _write_json(p, spec)
    return p, spec


def _make_seed(tmpdir, name="seed.json", seedval=1234):
    seed = {"seed": seedval}
    p = os.path.join(tmpdir, name)
    _write_json(p, seed)
    return p, seed


def _make_bundle(tmpdir):
    # create a bundle dir with spec + dna/meta
    bdir = os.path.join(tmpdir, "bundle")
    os.makedirs(bdir, exist_ok=True)
    _write_json(os.path.join(bdir, "spec.json"), {"name": "bundle-demo", "bankroll": 777})
    _write_json(os.path.join(bdir, "seed.json"), {"seed": 4242})
    Path(os.path.join(bdir, "dna")).mkdir(exist_ok=True)
    Path(os.path.join(bdir, "meta")).mkdir(exist_ok=True)
    with open(os.path.join(bdir, "dna", "notes.txt"), "wb") as f:
        f.write(b"hello-dna")
    with open(os.path.join(bdir, "meta", "marker.bin"), "wb") as f:
        f.write(b"\x00\x01\x02\x03")

    zip_path = os.path.join(tmpdir, "input_bundle.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(bdir):
            for fn in files:
                ap = os.path.join(root, fn)
                rel = os.path.relpath(ap, bdir).replace("\\", "/")
                z.write(ap, arcname=rel)
    return zip_path


def test_run_id_determinism(tmp_path):
    _, spec = _make_spec(tmp_path)
    _, seed = _make_seed(tmp_path)
    assert canonicalize_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    run_id1 = spec_seed_fingerprint(spec, seed, "engine-x", "csc-y")
    run_id2 = spec_seed_fingerprint(spec, seed, "engine-x", "csc-y")
    assert run_id1 == run_id2
    # small variation changes hash
    run_id3 = spec_seed_fingerprint(dict(spec, bankroll=spec["bankroll"]+1), seed, "engine-x", "csc-y")
    assert run_id3 != run_id1


def test_batch_spec_and_zip_inputs(tmp_path):
    # prepare inputs
    spec_path, _ = _make_spec(tmp_path, bankroll=1000)
    bundle_zip = _make_bundle(tmp_path)

    # plan as JSON to avoid yaml dep
    plan = {
        "items": [{"path": str(spec_path)}, {"path": str(bundle_zip)}],
        "out_dir": str(tmp_path / "exports"),
        "engine_version": "engine-x",
        "csc_version": "csc-y",
    }
    plan_path = tmp_path / "plan.json"
    _write_json(plan_path, plan)

    manifest = run_batch(str(plan_path))
    assert "items" in manifest and len(manifest["items"]) == 2
    # verify export subfolders and output zips exist
    for rec in manifest["items"]:
        assert rec["status"] in ("success", "error")
        if rec["status"] == "success":
            assert os.path.isdir(rec["artifacts_dir"])
            assert os.path.isfile(rec["output_zip"])


def test_zip_passthrough_preserves_bytes(tmp_path):
    bundle_zip = _make_bundle(tmp_path)
    out_root = tmp_path / "exports"
    os.makedirs(out_root, exist_ok=True)

    rec = run_single_bundle_or_spec(str(bundle_zip), str(out_root), engine_version="e", csc_version="c")
    assert rec["status"] == "success"
    out_zip = rec["output_zip"]
    assert os.path.isfile(out_zip)

    # Extract original and output dna/meta files and compare
    def read_entry(zp, name):
        with zipfile.ZipFile(zp, "r") as z:
            with z.open(name, "r") as f:
                return f.read()

    orig_dna = read_entry(bundle_zip, "dna/notes.txt")
    out_dna = read_entry(out_zip, "dna/notes.txt")
    assert orig_dna == out_dna

    orig_meta = read_entry(bundle_zip, "meta/marker.bin")
    out_meta = read_entry(out_zip, "meta/marker.bin")
    assert orig_meta == out_meta
