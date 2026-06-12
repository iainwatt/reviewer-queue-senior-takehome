"""Tests for the reviewer workflow rules from the README.

These cover the three notes.txt items:
  - only `in_review` can be approved/rejected/escalated
  - terminal items must not allow further actions
  - invalid actions are rejected cleanly

Seed item ids referenced (from data/review_items.json):
  unassigned: RV-1024 (high/priority), RV-1025, RV-1026, RV-1031, RV-1032, RV-1035
  in_review:  RV-1027 (sam), RV-1028 (morgan), RV-1030 (alex)
  approved:   RV-1029
  escalated:  RV-1033
  rejected:   RV-1034
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.main import (
    ActionRequest,
    apply_action,
    list_review_items,
    reset_items,
)


def run_async(coro):
    return asyncio.run(coro)


def call_action(item_id: str, action: str, reviewer: str = "alex") -> dict:
    request = ActionRequest(action=action, reviewer=reviewer)
    return run_async(apply_action(item_id, request))


def get_item(item_id: str) -> dict:
    response = run_async(list_review_items(active_only=False))
    return next(item for item in response["items"] if item["id"] == item_id)


@pytest.fixture(autouse=True)
def reset_seed_state():
    """Reset the in-memory store before every test so order does not matter."""
    run_async(reset_items())
    yield
    run_async(reset_items())


class TestClaim:
    def test_unassigned_item_can_be_claimed(self) -> None:
        response = call_action("RV-1024", "claim", reviewer="alex")

        assert response["item"]["status"] == "in_review"
        assert response["item"]["assigned_reviewer"] == "alex"

    def test_claim_persists_assignment_in_store(self) -> None:
        call_action("RV-1024", "claim", reviewer="alex")

        item = get_item("RV-1024")
        assert item["status"] == "in_review"
        assert item["assigned_reviewer"] == "alex"

    def test_cannot_claim_in_review_item(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            call_action("RV-1028", "claim", reviewer="alex")

        assert exc_info.value.status_code == 409

    def test_claim_does_not_overwrite_existing_assignee(self) -> None:
        # RV-1028 is in_review and assigned to morgan in the seed data.
        # alex must not be able to silently steal the item.
        assert get_item("RV-1028")["assigned_reviewer"] == "morgan"

        with pytest.raises(HTTPException):
            call_action("RV-1028", "claim", reviewer="alex")

        assert get_item("RV-1028")["assigned_reviewer"] == "morgan"

    @pytest.mark.parametrize(
        "item_id,starting_status",
        [
            ("RV-1029", "approved"),
            ("RV-1033", "escalated"),
            ("RV-1034", "rejected"),
        ],
    )
    def test_cannot_claim_terminal_item(self, item_id: str, starting_status: str) -> None:
        assert get_item(item_id)["status"] == starting_status

        with pytest.raises(HTTPException) as exc_info:
            call_action(item_id, "claim")

        assert exc_info.value.status_code == 409


class TestDecisionActions:
    @pytest.mark.parametrize(
        "action,expected_status",
        [
            ("approve", "approved"),
            ("reject", "rejected"),
            ("escalate", "escalated"),
        ],
    )
    def test_can_decide_in_review_item(self, action: str, expected_status: str) -> None:
        # RV-1028 is assigned to morgan, so morgan is the one who may decide it.
        response = call_action("RV-1028", action, reviewer="morgan")

        assert response["item"]["status"] == expected_status

    @pytest.mark.parametrize("action", ["approve", "reject", "escalate"])
    def test_cannot_decide_item_claimed_by_another_reviewer(self, action: str) -> None:
        # RV-1028 is in_review and assigned to morgan; alex must not be able to act on it.
        assert get_item("RV-1028")["assigned_reviewer"] == "morgan"

        with pytest.raises(HTTPException) as exc_info:
            call_action("RV-1028", action, reviewer="alex")

        assert exc_info.value.status_code == 403
        assert get_item("RV-1028")["status"] == "in_review"

    @pytest.mark.parametrize(
        "action,expected_status",
        [
            ("approve", "approved"),
            ("reject", "rejected"),
            ("escalate", "escalated"),
        ],
    )
    def test_assigned_reviewer_can_decide_own_item(
        self, action: str, expected_status: str
    ) -> None:
        # RV-1030 is in_review and assigned to alex in the seed data.
        assert get_item("RV-1030")["assigned_reviewer"] == "alex"

        response = call_action("RV-1030", action, reviewer="alex")

        assert response["item"]["status"] == expected_status

    @pytest.mark.parametrize("action", ["approve", "reject", "escalate"])
    def test_cannot_decide_unassigned_item(self, action: str) -> None:
        # RV-1024 starts as unassigned; only `claim` should be valid.
        with pytest.raises(HTTPException) as exc_info:
            call_action("RV-1024", action)

        assert exc_info.value.status_code == 409

    @pytest.mark.parametrize(
        "item_id,starting_status",
        [
            ("RV-1029", "approved"),
            ("RV-1033", "escalated"),
            ("RV-1034", "rejected"),
        ],
    )
    @pytest.mark.parametrize("action", ["approve", "reject", "escalate"])
    def test_cannot_decide_terminal_item(
        self,
        action: str,
        item_id: str,
        starting_status: str,
    ) -> None:
        assert get_item(item_id)["status"] == starting_status

        with pytest.raises(HTTPException) as exc_info:
            call_action(item_id, action)

        assert exc_info.value.status_code == 409


class TestInvalidActionRequest:
    def test_unknown_action_rejected_at_validation(self) -> None:
        with pytest.raises(ValidationError):
            ActionRequest(action="delete")  # type: ignore[arg-type]

    def test_empty_reviewer_rejected_at_validation(self) -> None:
        with pytest.raises(ValidationError):
            ActionRequest(action="claim", reviewer="")

    def test_unknown_item_id_returns_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            call_action("RV-DOES-NOT-EXIST", "claim")

        assert exc_info.value.status_code == 404


class TestActiveQueue:
    def test_active_queue_excludes_terminal_items(self) -> None:
        response = run_async(list_review_items(active_only=True))

        ids = {item["id"] for item in response["items"]}
        assert "RV-1029" not in ids  # approved
        assert "RV-1033" not in ids  # escalated
        assert "RV-1034" not in ids  # rejected

    def test_active_queue_sort_order(self) -> None:
        response = run_async(list_review_items(active_only=True))

        ordered_ids = [item["id"] for item in response["items"]]
        assert ordered_ids == [
            "RV-1024",  # high / priority / 2026-04-02 08:15
            "RV-1030",  # high / priority / 2026-04-02 11:55
            "RV-1025",  # high / standard / 2026-04-01 09:30
            "RV-1032",  # high / standard / 2026-04-01 17:20
            "RV-1035",  # medium / priority / 2026-04-02 06:50
            "RV-1026",  # medium / priority / 2026-04-03 07:20
            "RV-1028",  # medium / standard / 2026-04-01 14:05
            "RV-1027",  # low / standard / 2026-04-02 10:45
            "RV-1031",  # low / standard / 2026-04-03 08:40
        ]
