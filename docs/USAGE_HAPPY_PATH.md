## Human Summary & Scaffolding
```bash
python -m csc init myrun && cd myrun
python -m csc doctor --spec spec.json
python -m csc run --seed 4242 --spec spec.json --explain
python -m csc summarize --artifacts artifacts/latest --human
```

> ℹ️ `python -m crapssim_control.cli ...` remains available and behaves the same as the `python -m csc ...` alias.
