"""
Minimal FastAPI endpoint for external commands: POST /commands
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any

from crapssim_control.external.command_channel import CommandQueue
from crapssim_control.rules_engine.actions import ACTIONS  # for verb whitelist


def create_app(queue: CommandQueue, active_run_id_supplier) -> FastAPI:
    app = FastAPI()

    @app.post("/commands")
    async def post_commands(req: Request):
        body: Dict[str, Any] = await req.json()
        # run_id check
        active_run_id = active_run_id_supplier()
        if not active_run_id or body.get("run_id") != active_run_id:
            return JSONResponse({"status": "rejected", "reason": "run_id_mismatch"}, status_code=400)
        # action verb check
        verb = body.get("action")
        if verb not in ACTIONS:
            return JSONResponse({"status": "rejected", "reason": "unknown_action"}, status_code=400)
        ok, reason = queue.enqueue(body)
        if not ok:
            return JSONResponse({"status": "rejected", "reason": reason}, status_code=400)
        return JSONResponse({"status": "queued"}, status_code=202)

    return app
