# Contributing

Thanks for considering a contribution! This doc keeps things quick and smooth.

## Getting Started
1. **Fork** the repo and create a topic branch from `main`.
2. **Python**: 3.11+ is recommended.
3. Create a virtualenv:  
   ```bash
   python -m venv .venv && . .venv/bin/activate
   pip install -U pip
   pip install -e .[dev]

	4.	Run tests:

pytest -q



Development Tips
	•	Lint/format if you use them locally (optional): ruff, black.
	•	Keep PRs focused; smaller PRs get merged faster.
	•	Include/adjust tests when changing behavior or messages the tests assert on.
	•	For spec changes, update SPEC.md.

Commit Messages

Follow conventional style when possible:
	•	fix: …, feat: …, docs: …, refactor: …, test: …, chore: …

Pull Requests
	•	Link issues when relevant.
	•	Describe what changed and why.
	•	Make sure CI is green.

Releasing (maintainers)
	•	Update version in crapssim_control/__init__.py.
	•	Update CHANGELOG.md.
	•	Tag vX.Y.Z and publish to PyPI if appropriate.

Code of Conduct

By contributing, you agree to abide by our Code of Conduct.

—