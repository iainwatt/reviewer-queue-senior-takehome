from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "review_items.json"

ReviewAction = Literal["claim", "approve", "reject", "escalate"]

TERMINAL_STATUSES = frozenset({"approved", "rejected", "escalated"})

RISK_RANK = {"high": 0, "medium": 1, "low": 2}
TIER_RANK = {"priority": 0, "standard": 1}


def queue_sort_key(item: dict) -> tuple[int, int, str]:
    return (
        RISK_RANK.get(item["risk_level"], 99),
        TIER_RANK.get(item["customer_tier"], 99),
        item["submitted_at"],
    )


ALLOWED_TRANSITIONS: dict[str, dict[str, str]] = {
    "claim": {"unassigned": "in_review"},
    "approve": {"in_review": "approved"},
    "reject": {"in_review": "rejected"},
    "escalate": {"in_review": "escalated"},
}


class ActionRequest(BaseModel):
    action: ReviewAction
    reviewer: str = Field(default="alex", min_length=1)


app = FastAPI(title="Reviewer Queue API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_seed_items() -> list[dict]:
    with DATA_FILE.open() as file:
        return json.load(file)


ITEMS = load_seed_items()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/dev/reset")
async def reset_items() -> dict:
    global ITEMS
    ITEMS = load_seed_items()
    return {"items": deepcopy(ITEMS)}


@app.get("/review-items")
async def list_review_items(active_only: bool = True) -> dict:
    items = deepcopy(ITEMS)

    if active_only:
        items = [item for item in items if item["status"] not in TERMINAL_STATUSES]

    items.sort(key=queue_sort_key)
    return {"items": items}


@app.get("/review-items/{item_id}")
async def get_review_item(item_id: str) -> dict:
    item = find_item(item_id)
    return {"item": deepcopy(item)}


@app.post("/review-items/{item_id}/actions")
async def apply_action(item_id: str, request: ActionRequest) -> dict:
    item = find_item(item_id)

    transitions = ALLOWED_TRANSITIONS[request.action]
    next_status = transitions.get(item["status"])
    if next_status is None:
        allowed = sorted(transitions)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot {request.action} an item with status '{item['status']}'. "
                f"Allowed from: {allowed}."
            ),
        )

    # TAKEHOME: Only the reviewer who claimed an item may act on it. Without this
    # check any reviewer could approve/reject/escalate work owned by someone else.
    if request.action != "claim" and item["assigned_reviewer"] != request.reviewer:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Cannot {request.action} an item claimed by "
                f"'{item['assigned_reviewer']}'. Only the assigned reviewer may act on it."
            ),
        )

    item["status"] = next_status
    if request.action == "claim":
        item["assigned_reviewer"] = request.reviewer

    return {"item": deepcopy(item)}


def find_item(item_id: str) -> dict:
    for item in ITEMS:
        if item["id"] == item_id:
            return item
    raise HTTPException(status_code=404, detail="Review item not found")
