"""Ready-made workflow templates.

Each preset is a fully wired graph (agents + steps + transitions) a user can
drop into their organization to see how workflows are put together, then tweak
to taste. Presets are applied as DRAFT definitions (see the
`/workflows/from-preset` route), so the user still edits and activates them.

Agents are referenced by name: applying a preset reuses an existing agent with
a matching name, or creates it if it doesn't exist yet.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PresetStep:
    key: str
    name: str
    agent: str
    description: str
    is_initial: bool = False
    is_terminal: bool = False


@dataclass(frozen=True)
class PresetTransition:
    from_key: str
    to_key: str
    action_name: str
    description: str | None = None


@dataclass(frozen=True)
class WorkflowPreset:
    key: str
    name: str
    description: str
    icon: str
    # (agent name, agent description)
    agents: tuple[tuple[str, str], ...]
    steps: tuple[PresetStep, ...]
    transitions: tuple[PresetTransition, ...]


WORKFLOW_PRESETS: tuple[WorkflowPreset, ...] = (
    WorkflowPreset(
        key="standard-contract",
        name="Standard Contract Lifecycle",
        description="Draft → Negotiate → Sign → Store, with Renew/Amend loops and a Terminate → Archive → Destruct tail.",
        icon="file-text",
        agents=(
            ("Drafting", "Authors and edits the initial document draft."),
            ("Negotiation", "Negotiates terms with the counterparty."),
            ("Signatory", "Collects binding signatures."),
            ("Records Management", "Holds active, signed contracts of record."),
            ("Renewals", "Handles renewal requests for active contracts."),
            ("Amendments", "Handles amendment requests for active contracts."),
            ("Termination", "Processes contract termination."),
            ("Archive", "Retains terminated contracts for the retention period."),
            ("Destruction", "Permanently destroys contracts past retention."),
        ),
        steps=(
            PresetStep("draft", "Draft", "Drafting", "Legal authors the initial contract text.", is_initial=True),
            PresetStep("negotiate", "Negotiate", "Negotiation", "Terms are discussed with the counterparty."),
            PresetStep("sign", "Sign", "Signatory", "Both parties collect binding signatures."),
            PresetStep("store", "Store", "Records Management", "The signed contract is active and on file."),
            PresetStep("renew", "Renew", "Renewals", "A renewal request is reviewed before expiry."),
            PresetStep("amend", "Amend", "Amendments", "A change to the active contract is reviewed."),
            PresetStep("terminate", "Terminate", "Termination", "The contract is being wound down."),
            PresetStep("archive", "Archive", "Archive", "Kept on file for the retention period."),
            PresetStep("destruct", "Destruct", "Destruction", "Permanently destroyed past retention.", is_terminal=True),
        ),
        transitions=(
            PresetTransition("draft", "negotiate", "send_for_negotiation"),
            PresetTransition("negotiate", "sign", "approve"),
            PresetTransition("negotiate", "draft", "request_changes"),
            PresetTransition("sign", "store", "complete_signature"),
            PresetTransition("store", "renew", "request_renewal"),
            PresetTransition("store", "amend", "request_amendment"),
            PresetTransition("store", "terminate", "initiate_termination"),
            PresetTransition("renew", "store", "approve_renewal"),
            PresetTransition("renew", "terminate", "reject_renewal"),
            PresetTransition("amend", "store", "approve_amendment"),
            PresetTransition("terminate", "archive", "finalize_termination"),
            PresetTransition("archive", "destruct", "schedule_destruction"),
        ),
    ),
    WorkflowPreset(
        key="simple-approval",
        name="Simple Approval",
        description="A minimal Draft → Review → Approved flow with a request-changes loop back to Draft.",
        icon="check",
        agents=(
            ("Author", "Prepares the document for review."),
            ("Reviewer", "Reviews and approves or sends the document back."),
        ),
        steps=(
            PresetStep("draft", "Draft", "Author", "The author prepares the document.", is_initial=True),
            PresetStep("review", "Review", "Reviewer", "A reviewer checks the document."),
            PresetStep("approved", "Approved", "Reviewer", "The document is approved and final.", is_terminal=True),
        ),
        transitions=(
            PresetTransition("draft", "review", "submit", "Send the draft for review."),
            PresetTransition("review", "approved", "approve", "Approve the document."),
            PresetTransition("review", "draft", "request_changes", "Send it back with feedback."),
        ),
    ),
    WorkflowPreset(
        key="procurement",
        name="Procurement Request",
        description="Request → Approval → Purchasing → Received, with a rejection loop back to the requester.",
        icon="layers",
        agents=(
            ("Requester", "Raises the purchase request."),
            ("Approvals", "Approves or rejects the spend."),
            ("Purchasing", "Places the order with the supplier."),
            ("Receiving", "Confirms delivery of goods or services."),
        ),
        steps=(
            PresetStep("request", "Request", "Requester", "A purchase request is raised.", is_initial=True),
            PresetStep("approval", "Approval", "Approvals", "The spend is approved or rejected."),
            PresetStep("purchasing", "Purchasing", "Purchasing", "The order is placed with the supplier."),
            PresetStep("received", "Received", "Receiving", "Goods or services are confirmed received.", is_terminal=True),
        ),
        transitions=(
            PresetTransition("request", "approval", "submit", "Submit the request for approval."),
            PresetTransition("approval", "purchasing", "approve", "Approve the spend."),
            PresetTransition("approval", "request", "reject", "Send it back to the requester."),
            PresetTransition("purchasing", "received", "confirm_delivery", "Confirm the order arrived."),
        ),
    ),
)

PRESETS_BY_KEY: dict[str, WorkflowPreset] = {preset.key: preset for preset in WORKFLOW_PRESETS}
