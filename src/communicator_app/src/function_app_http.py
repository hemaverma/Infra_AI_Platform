"""HTTP trigger: local end-to-end test twin of the Service Bus workflow trigger."""
import json

import azure.functions as func
from workflow_runner import handle_workflow_message

bp = func.Blueprint()


@bp.route(route="workflow-queue", methods=["POST"])
async def workflow_queue_consumer_http(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP twin of `workflow_queue_consumer` for local end-to-end testing.

    Accepts the same envelope shapes as the SB trigger and returns the
    `hitl-queue` envelopes that would have been published in the response body,
    so callers can inspect transport without binding to Service Bus.
    Production deployments set ENABLE_HTTP_TEST_TRIGGERS=false.
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "request body must be valid JSON"}),
            status_code=400,
            mimetype="application/json",
        )
    try:
        result = await handle_workflow_message(body)
    except ValueError as exc:
        return func.HttpResponse(
            json.dumps({"error": str(exc)}),
            status_code=400,
            mimetype="application/json",
        )
    return func.HttpResponse(
        json.dumps({"result": result}),
        status_code=200,
        mimetype="application/json",
    )
