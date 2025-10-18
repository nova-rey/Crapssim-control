# Run Manifest Schema

Every exported run includes a `manifest.json` describing the environment, CLI configuration, and schema versions.

### Example
```json
{
  "run_id": "d50b9d19-f7cb-4a1d-b34c-87c91499e925",
  "timestamp": "2025-10-18T12:00:00Z",
  "spec_file": "examples/quickstart_spec.json",
  "cli_flags": {
    "strict": false,
    "demo_fallbacks": false,
    "embed_analytics": true,
    "export": true
  },
  "schema": {
    "journal": "1.2",
    "summary": "1.2"
  },
  "engine_version": "CrapsSim-Control",
  "output_paths": {
    "journal": "export/journal.csv",
    "report": "export/report.json",
    "manifest": "export/manifest.json"
  }
}
```

Purpose

The manifest provides traceability between CLI invocation, schema version, and generated artifacts.
External systems (Node-RED, CrapsSim-Evo) can use this file to programmatically locate outputs and understand configuration context.
