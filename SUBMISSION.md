# Submission

## Summary of changes

Fixed reviewer workflow transitions and active queue ordering.
Added UI action gating so reviewers only see valid actions for the selected item.
Improved queue scanning with risk indicators, ownership highlighting, and a cleared-queue state.

## Bugs fixed

Terminal items are now excluded from the active queue and cannot be changed again.
Claims are only allowed from `unassigned` and record the acting reviewer.
Approve, reject, and escalate are only allowed from `in_review` and return clean `409` errors otherwise.

## Product/UX decisions

The queue now reinforces urgency visually with risk color, badges, and clearer item ownership.
Invalid actions are hidden instead of making reviewers discover rules through failed requests.
Completed decisions remove the item from the active queue so the reviewer can keep moving.

## Tests added

Added backend workflow tests for valid claims and decision actions.
Added rejection tests for unassigned, in-review, terminal, unknown-item, and invalid-action cases.
Added active queue tests for terminal filtering and required urgency ordering.

## Known gaps

The app still uses an in-memory store and a hardcoded current reviewer, as allowed by the exercise.
Frontend behavior is covered by build/type checks, not dedicated component tests.
Would have liked to add filters and moved in reivew items to a different place or demarked differently. Lots of stuff to be done on backend like data modelling that lacked time to consider.

## Files changed and why

`backend/app/main.py`: centralized workflow rules, terminal filtering, queue sorting, and validation.
`backend/tests/test_workflow.py`: covers the business rules and high-risk state transitions.
`frontend/src/App.vue` and `frontend/src/styles.css`: added action gating and queue clarity improvements.

## AI assistance used

I used AI to inspect the README, identify workflow risks, and prioritize the implementation plan.
AI helped draft targeted tests and review the UI changes against the take-home requirements.
I reviewed and verified the changes locally with `pytest` and `npm run build`.
