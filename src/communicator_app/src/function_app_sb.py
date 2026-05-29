"""Service Bus trigger: consume `workflow-queue` and emit `hitl-queue` envelopes."""
import json
import logging

import azure.functions as func
from workflow_runner import handle_workflow_message

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="%WorkflowQueueName%",
    connection="ServiceBusConnection",
)
@bp.service_bus_queue_output(
    arg_name="hitlOut",
    queue_name="%HitlQueueName%",
    connection="ServiceBusConnection",
)
async def workflow_queue_consumer(
    msg: func.ServiceBusMessage,
    hitlOut: func.Out[str],
) -> None:
    """Consume `workflow-queue`; emit one `hitl-queue` envelope per pending request_info.

    Unknown `eventType` raises `ValueError`; Service Bus retries with
    exponential backoff per the queue policy and eventually dead-letters
    (architecture.md §3.5). Any exception escaping this function aborts the
    inbound message and prevents partial emission to `hitl-queue`.

    Note: the Azure Functions Python output binding only accepts plain
    `str`/`bytes` annotations (DD-07 — the binding registry calls
    `issubclass(pytype, (str, bytes))` which rejects generic aliases). Today
    every paused superstep produces exactly one `request_info` event because
    the V1 graph is strictly linear, so the JSON-array body is always length
    1 in practice. The assertion below makes that invariant explicit and
    fails loudly the moment a future graph (e.g., parallel HITL approvals,
    per-item fan-out, multi-reviewer draft) emits N>1 in a single drain;
    that PR must replace the output binding with an explicit
    `ServiceBusSender.send_messages(...)` call so each envelope ships as its
    own SB message per architecture.md §3.4. Tracked as STORY-26.
    """
    body = json.loads(msg.get_body().decode("utf-8"))
    result = await handle_workflow_message(body)
    hitl_messages = result.get("hitl_messages", [])
    assert len(hitl_messages) <= 1, (
        f"workflow_queue_consumer emitted {len(hitl_messages)} hitl envelopes "
        "in one drain; the func.Out[str] binding can only carry one SB "
        "message per invocation. See STORY-26 — switch to explicit "
        "ServiceBusSender.send_messages before merging any graph that produces "
        "multiple request_info events per superstep."
    )
    if hitl_messages:
        hitlOut.set(json.dumps(hitl_messages[0]))
    logger.info(
        "workflow_queue_consumer status=%s hitl_messages=%d",
        result.get("status"),
        len(hitl_messages),
    )
