<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  applyReviewAction,
  fetchReviewItems,
  type ReviewAction,
  type ReviewItem,
  type ReviewStatus
} from "./api";

const currentReviewer = "alex";
const items = ref<ReviewItem[]>([]);
const selectedId = ref<string | null>(null);
const isLoading = ref(false);
const errorMessage = ref<string | null>(null);
const pendingAction = ref<ReviewAction | null>(null);

// TAKEHOME: Mirrors the backend's ALLOWED_TRANSITIONS so the UI only offers
// actions the server will accept. Keep these two in sync when adding states.
const ALLOWED_ACTIONS_BY_STATUS: Record<ReviewStatus, ReviewAction[]> = {
  unassigned: ["claim"],
  in_review: ["approve", "reject", "escalate"],
  approved: [],
  rejected: [],
  escalated: []
};

const ACTION_LABELS: Record<ReviewAction, string> = {
  claim: "Claim",
  approve: "Approve",
  reject: "Reject",
  escalate: "Escalate"
};

const TERMINAL_ACTIONS: ReadonlySet<ReviewAction> = new Set([
  "approve",
  "reject",
  "escalate"
]);

const selectedItem = computed(() =>
  items.value.find((item) => item.id === selectedId.value) ?? items.value[0] ?? null
);

const availableActions = computed<ReviewAction[]>(() =>
  selectedItem.value ? ALLOWED_ACTIONS_BY_STATUS[selectedItem.value.status] : []
);

async function loadItems() {
  isLoading.value = true;
  errorMessage.value = null;

  try {
    items.value = await fetchReviewItems();
    selectedId.value = selectedItem.value?.id ?? null;
  } catch (error) {
    errorMessage.value = "Something went wrong loading the queue.";
  } finally {
    isLoading.value = false;
  }
}

async function performAction(action: ReviewAction) {
  if (!selectedItem.value) return;
  const actingItemId = selectedItem.value.id;

  pendingAction.value = action;
  errorMessage.value = null;

  try {
    const updated = await applyReviewAction(actingItemId, action, currentReviewer);

    if (TERMINAL_ACTIONS.has(action)) {
      // Item is now in a terminal state; the active queue must not show it.
      // Auto-select the next item at the same position so the reviewer keeps moving.
      const removedIndex = items.value.findIndex((item) => item.id === actingItemId);
      const remaining = items.value.filter((item) => item.id !== actingItemId);
      items.value = remaining;

      const next =
        remaining[removedIndex] ?? remaining[remaining.length - 1] ?? null;
      selectedId.value = next?.id ?? null;
    } else {
      items.value = items.value.map((item) => (item.id === updated.id ? updated : item));
      selectedId.value = updated.id;
    }
  } catch (error) {
    errorMessage.value = "That action could not be completed.";
  } finally {
    pendingAction.value = null;
  }
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

onMounted(loadItems);
</script>

<template>
  <main class="page-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">Reviewer workspace</p>
        <h1>Active queue</h1>
      </div>
      <div class="reviewer">Signed in as {{ currentReviewer }}</div>
    </header>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>
    <p v-if="isLoading" class="loading">Loading review items...</p>

    <section v-else class="workspace">
      <aside class="queue-list" aria-label="Review queue">
        <button
          v-for="item in items"
          :key="item.id"
          class="queue-item"
          :class="[`risk-${item.risk_level}`, { selected: item.id === selectedItem?.id, 'mine': item.assigned_reviewer === currentReviewer }]"
          type="button"
          @click="selectedId = item.id"
        >
          <span class="queue-title">
            <span class="risk-flag" :class="`risk-flag-${item.risk_level}`" aria-hidden="true"></span>
            {{ item.title }}
            <span v-if="item.assigned_reviewer === currentReviewer" class="mine-badge">Assigned to you</span>
          </span>
          <span class="queue-meta">
            <span class="risk-badge" :class="`risk-badge-${item.risk_level}`">{{ item.risk_level }} risk</span>
            · {{ item.customer_tier }}
          </span>
          <span class="queue-meta">{{ item.status }} · {{ item.assigned_reviewer ?? "unassigned" }}</span>
        </button>
      </aside>

      <section v-if="selectedItem" class="detail-panel" :class="`risk-${selectedItem.risk_level}`">
        <div class="detail-header">
          <div>
            <p class="eyebrow">{{ selectedItem.id }}</p>
            <h2>{{ selectedItem.title }}</h2>
          </div>
          <span class="status-pill">{{ selectedItem.status }}</span>
        </div>

        <dl class="facts">
          <div>
            <dt>Submitted</dt>
            <dd>{{ formatDate(selectedItem.submitted_at) }}</dd>
          </div>
          <div>
            <dt>Risk</dt>
            <dd>{{ selectedItem.risk_level }}</dd>
          </div>
          <div>
            <dt>Customer</dt>
            <dd>{{ selectedItem.customer_tier }}</dd>
          </div>
          <div>
            <dt>Assignee</dt>
            <dd>{{ selectedItem.assigned_reviewer ?? "None" }}</dd>
          </div>
        </dl>

        <p class="summary">{{ selectedItem.summary }}</p>
        <p class="notes">{{ selectedItem.notes_count }} notes on this item</p>

        <div class="actions" aria-label="Workflow actions">
          <button
            v-for="action in availableActions"
            :key="action"
            type="button"
            :class="['action-button', `action-${action}`]"
            :disabled="Boolean(pendingAction)"
            @click="performAction(action)"
          >
            {{ pendingAction === action ? "Working..." : ACTION_LABELS[action] }}
          </button>
          <p v-if="availableActions.length === 0" class="no-actions">
            No actions available for this item.
          </p>
        </div>
      </section>

      <section v-else class="detail-panel empty-state">
        <h2>Queue cleared</h2>
        <p>There are no active review items. Nice work.</p>
      </section>
    </section>
  </main>
</template>
