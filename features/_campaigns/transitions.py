"""Canonical campaign workflow graph — nodes, edges, and stage rules."""

import re

WORKFLOW_ENTRY_NODE = "lead-list"

# Template ids in canvas order (includes terminal CRM sinks).
WORKFLOW_NODE_IDS = (
    "lead-list",
    "phone-lookup",
    "compliance-gate",
    "call-queue",
    "dialing",
    "in-conversation",
    "outcome-router",
    "retry-scheduler",
    "qualify-prioritize",
    "qualified-crm",
    "disqualified-crm",
    "excluded-crm",
)

# Fixed directed edges (not user-editable). from_socket uses workflow socket slug (see slug_socket).
WORKFLOW_EDGES = (
    {"id": "e-lead-phone", "from": "lead-list", "to": "phone-lookup", "from_socket": "out", "to_socket": "in"},
    {
        "id": "e-phone-compliance",
        "from": "phone-lookup",
        "to": "compliance-gate",
        "from_socket": "out-business-line",
        "to_socket": "in",
    },
    {
        "id": "e-phone-excluded",
        "from": "phone-lookup",
        "to": "excluded-crm",
        "from_socket": "out-excluded",
        "to_socket": "in",
    },
    {
        "id": "e-compliance-queue",
        "from": "compliance-gate",
        "to": "call-queue",
        "from_socket": "out-pass",
        "to_socket": "in",
    },
    {
        "id": "e-compliance-excluded",
        "from": "compliance-gate",
        "to": "excluded-crm",
        "from_socket": "out-blocked",
        "to_socket": "in",
    },
    {"id": "e-queue-dialing", "from": "call-queue", "to": "dialing", "from_socket": "out", "to_socket": "in"},
    {
        "id": "e-dialing-conversation",
        "from": "dialing",
        "to": "in-conversation",
        "from_socket": "out-answered",
        "to_socket": "in",
    },
    {
        "id": "e-dialing-outcome",
        "from": "dialing",
        "to": "outcome-router",
        "from_socket": "out-no-answer-vm-failed",
        "to_socket": "in",
    },
    {
        "id": "e-conversation-outcome",
        "from": "in-conversation",
        "to": "outcome-router",
        "from_socket": "out",
        "to_socket": "in",
    },
    {
        "id": "e-outcome-retry",
        "from": "outcome-router",
        "to": "retry-scheduler",
        "from_socket": "out-retry",
        "to_socket": "in",
    },
    {
        "id": "e-outcome-qualify",
        "from": "outcome-router",
        "to": "qualify-prioritize",
        "from_socket": "out-answered",
        "to_socket": "in",
    },
    {
        "id": "e-outcome-disqualified",
        "from": "outcome-router",
        "to": "disqualified-crm",
        "from_socket": "out-disqualified",
        "to_socket": "in",
    },
    {
        "id": "e-outcome-excluded",
        "from": "outcome-router",
        "to": "excluded-crm",
        "from_socket": "out-excluded",
        "to_socket": "in",
    },
    {
        "id": "e-retry-queue",
        "from": "retry-scheduler",
        "to": "call-queue",
        "from_socket": "out-back-to-queue",
        "to_socket": "in",
    },
    {
        "id": "e-qualify-qualified",
        "from": "qualify-prioritize",
        "to": "qualified-crm",
        "from_socket": "out-qualified",
        "to_socket": "in",
    },
)

_EDGE_BY_ID = {row["id"]: row for row in WORKFLOW_EDGES}
_OUT_EDGES = {}
for _edge in WORKFLOW_EDGES:
    _OUT_EDGES.setdefault(_edge["from"], []).append(_edge)


def slug_socket(label):
    slug = re.sub(r"[^a-z0-9]+", "-", str(label or "").lower()).strip("-")
    return f"out-{slug}" if slug else "out"


def socket_for_output(label, multi):
    if not multi:
        return "out"
    return slug_socket(label)


def is_valid_node(node_id):
    return node_id in WORKFLOW_NODE_IDS


def edge_by_id(edge_id):
    return _EDGE_BY_ID.get(edge_id)


def outgoing_edges(node_id):
    return list(_OUT_EDGES.get(node_id) or [])


def is_allowed_transition(from_node, to_node, from_socket):
    for edge in outgoing_edges(from_node):
        if edge["to"] == to_node and edge["from_socket"] == from_socket:
            return edge
    return None


def _member_node(stages, lead_id, default=WORKFLOW_ENTRY_NODE):
    if not isinstance(stages, dict):
        return default
    row = stages.get(lead_id)
    if isinstance(row, str):
        return row if is_valid_node(row) else default
    if isinstance(row, dict):
        node = row.get("node") or row.get("stage")
        if is_valid_node(node):
            return node
    return default


def _member_branch(stages, lead_id):
    if not isinstance(stages, dict):
        return None
    row = stages.get(lead_id)
    if isinstance(row, dict):
        branch = row.get("branch") or row.get("socket")
        return str(branch).strip() if branch else None
    return None


def _edge_lane_for_member(lead_id, edges):
    if len(edges) <= 1:
        return edges[0]["from_socket"] if edges else None
    digest = sum(ord(ch) for ch in str(lead_id)) % len(edges)
    return edges[digest]["from_socket"]


def build_flow_snapshot(lead_ids, stages=None):
    """Count members on each node and on each outgoing edge (mock branch split when unset)."""
    stages = stages if isinstance(stages, dict) else {}
    lead_ids = [str(lid) for lid in (lead_ids or []) if str(lid).strip()]

    nodes = {node_id: {"count": 0, "lead_ids": []} for node_id in WORKFLOW_NODE_IDS}
    edges = {row["id"]: {"count": 0, "lead_ids": [], **row} for row in WORKFLOW_EDGES}

    for lid in lead_ids:
        node = _member_node(stages, lid)
        if node not in nodes:
            node = WORKFLOW_ENTRY_NODE
        nodes[node]["count"] += 1
        nodes[node]["lead_ids"].append(lid)

        out = outgoing_edges(node)
        if not out:
            continue
        branch = _member_branch(stages, lid)
        if branch:
            chosen = next((e for e in out if e["from_socket"] == branch), None)
        elif len(out) == 1:
            chosen = out[0]
        else:
            lane = _edge_lane_for_member(lid, out)
            chosen = next((e for e in out if e["from_socket"] == lane), out[0])
        if chosen:
            bucket = edges[chosen["id"]]
            bucket["count"] += 1
            bucket["lead_ids"].append(lid)

    return {
        "entry_node": WORKFLOW_ENTRY_NODE,
        "nodes": nodes,
        "edges": edges,
        "edge_list": WORKFLOW_EDGES,
    }