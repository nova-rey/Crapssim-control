# Webhook / Node-RED Integration (Opt-In)

This optional integration emits small JSON POSTs at run lifecycle events. It is **disabled by default** and safe to ignore if not configured.

## Enabling
```bash
python -m crapssim_control.cli run examples/quickstart_spec.json \
  --export \
  --webhook-url http://localhost:1880/hook \
  --webhook-timeout 2.0
```

Events
- run.started — payload: { "spec": "<path>", "manifest_path": "export/manifest.json" }
- hand.started — { "hand_id": N }
- roll.processed — { "hand_id": N, "roll_in_hand": M }
- hand.finished — { "hand_id": N }
- run.finished — { "summary_schema_version": "1.2", "journal_schema_version": "1.2" }

Safety & Privacy
- If no URL or --no-webhook is set, no requests are made.
- Failures are swallowed; simulation continues.
- URL is not written into reports; only url_present: true appears in the manifest.
