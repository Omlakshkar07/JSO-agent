"""
event_listener.py
─────────────────────────────────────────────
PURPOSE:
  Listens for Supabase Realtime events (new reviews,
  placement updates) and triggers re-evaluations.
  Implements event-driven re-evaluation per PRD §FR-002, FR-003.

RESPONSIBILITIES:
  - Subscribe to review insert events
  - Subscribe to placement update events
  - Trigger re-evaluation via orchestrator

NOT RESPONSIBLE FOR:
  - Evaluation logic (see orchestrator.py)
  - Cron scheduling (see main.py or external scheduler)

DEPENDENCIES:
  - agent.orchestrator: run_evaluation
  - models.inputs: EvaluationTrigger
  - utils.logger

USED BY:
  - main.py (startup event listener)
─────────────────────────────────────────────
"""

from models.inputs import EvaluationTrigger
from agent.orchestrator import run_evaluation
from utils.logger import get_logger

logger = get_logger("api.event_listener")


def handle_new_review(payload: dict) -> None:
    """
    Handle a new review submission event.

    Triggered by Supabase Realtime when a row is inserted
    into the reviews table. Queues a re-evaluation for
    the affected agency.

    Args:
        payload: The Supabase Realtime event payload.
                 Expected shape: {"record": {"agency_id": "..."}}
    """
    record = payload.get("record", {})
    agency_id = record.get("agency_id")
    if not agency_id:
        logger.warning("New review event missing agency_id")
        return

    logger.info(
        "New review event received",
        extra={"extra_data": {"agency_id": agency_id}},
    )

    trigger = EvaluationTrigger(
        agency_id=agency_id,
        trigger_type="NEW_REVIEW",
        requestor_role="admin",
    )

    try:
        run_evaluation(trigger)
    except Exception as exc:
        logger.error(
            f"Re-evaluation failed after new review: {exc}",
            extra={"extra_data": {"agency_id": agency_id}},
        )


def handle_placement_update(payload: dict) -> None:
    """
    Handle a placement record update event.

    Triggered by Supabase Realtime when a row is inserted
    or updated in the placements table.

    Args:
        payload: The Supabase Realtime event payload.
    """
    record = payload.get("record", {})
    agency_id = record.get("agency_id")
    if not agency_id:
        logger.warning("Placement update event missing agency_id")
        return

    logger.info(
        "Placement update event received",
        extra={"extra_data": {"agency_id": agency_id}},
    )

    trigger = EvaluationTrigger(
        agency_id=agency_id,
        trigger_type="PLACEMENT_UPD",
        requestor_role="admin",
    )

    try:
        run_evaluation(trigger)
    except Exception as exc:
        logger.error(
            f"Re-evaluation failed after placement update: {exc}",
            extra={"extra_data": {"agency_id": agency_id}},
        )
