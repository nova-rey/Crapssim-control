# Node-RED Flow Demo

1. Import `flow.json` into Node-RED.
2. Start CSC with `run.webhooks.enabled=true` and `run.http_commands.enabled=true`.
3. The flow listens on `/webhook` and sends POSTs to `/commands` when bankroll < 900.
