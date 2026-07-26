"""Idempotent demo data: one organization, the 9 default agents, and an
ACTIVE 'Standard Contract Lifecycle' workflow wired as a graph (not a
straight line) so renewals/amendments loop back to Store and rejected
negotiations loop back to Draft.

Run with: uv run python -m app.infrastructure.seed
"""

import asyncio

from app.api.deps import (
    agent_service,
    document_service,
    organization_service,
    role_service,
    storage_service,
    user_service,
    workflow_service,
)
from app.domain.shared.exceptions import NotFoundError
from app.domain.storage.models import StorageProvider

ORG_NAME = "Acme Corp"

# Roles demonstrate the permission rule: "Draft" and "Sign" are gated to a
# specific role via `linked_agent`; every other step's agent has no role
# linked to it, so it stays open to anyone signed in (including "staff",
# whose role isn't linked to any agent at all).
ROLE_DEFINITIONS = [
    ("Drafting Lead", "Can act on the Draft step.", "Drafting"),
    ("Signatory Lead", "Can act on the Sign step.", "Signatory"),
    ("General Staff", "No agent link — can act on any step nobody else is gating.", None),
]

USER_DEFINITIONS = [
    ("Dana Drafter", "drafter@acme.test", "password123", "Drafting Lead"),
    ("Sam Signer", "signer@acme.test", "password123", "Signatory Lead"),
    ("Riley Staff", "staff@acme.test", "password123", "General Staff"),
]

AGENT_NAMES = [
    ("Drafting", "Authors and edits the initial document draft."),
    ("Negotiation", "Negotiates terms with the counterparty."),
    ("Signatory", "Collects binding signatures."),
    ("Records Management", "Holds active, signed contracts of record."),
    ("Renewals", "Handles renewal requests for active contracts."),
    ("Amendments", "Handles amendment requests for active contracts."),
    ("Termination", "Processes contract termination."),
    ("Archive", "Retains terminated contracts for the retention period."),
    ("Destruction", "Permanently destroys contracts past retention."),
]

STEP_DEFINITIONS = [
    ("draft", "Draft", "Drafting", "Legal authors the initial contract text.", True, False),
    ("negotiate", "Negotiate", "Negotiation", "Terms are discussed with the counterparty.", False, False),
    ("sign", "Sign", "Signatory", "Both parties collect binding signatures.", False, False),
    ("store", "Store", "Records Management", "The signed contract is active and on file.", False, False),
    ("renew", "Renew", "Renewals", "A renewal request is reviewed before expiry.", False, False),
    ("amend", "Amend", "Amendments", "A change to the active contract is reviewed.", False, False),
    ("terminate", "Terminate", "Termination", "The contract is being wound down.", False, False),
    ("archive", "Archive", "Archive", "Kept on file for the retention period.", False, False),
    ("destruct", "Destruct", "Destruction", "Permanently destroyed past retention.", False, True),
]

TRANSITION_DEFINITIONS = [
    ("draft", "negotiate", "send_for_negotiation", None),
    ("negotiate", "sign", "approve", None),
    ("negotiate", "draft", "request_changes", None),
    ("sign", "store", "complete_signature", None),
    ("store", "renew", "request_renewal", None),
    ("store", "amend", "request_amendment", None),
    ("store", "terminate", "initiate_termination", None),
    ("renew", "store", "approve_renewal", None),
    ("renew", "terminate", "reject_renewal", None),
    ("amend", "store", "approve_amendment", None),
    ("amend", "store", "reject_amendment", None),
    ("terminate", "archive", "finalize_termination", None),
    ("archive", "destruct", "schedule_destruction", None),
]


async def main() -> None:
    try:
        organization = await organization_service.get_by_slug("acme-corp")
        print(f"Organization '{organization.name}' already exists — nothing to seed.")
        return
    except NotFoundError:
        pass

    organization = await organization_service.create_organization(ORG_NAME)
    print(f"Created organization: {organization.name} ({organization.slug})")

    agents_by_name = {}
    for name, description in AGENT_NAMES:
        agent = await agent_service.create_agent(organization.id, name, description)
        agents_by_name[name] = agent
    print(f"Created {len(agents_by_name)} agents")

    roles_by_name = {}
    for name, description, linked_agent in ROLE_DEFINITIONS:
        agent_id = agents_by_name[linked_agent].id if linked_agent else None
        role = await role_service.create_role(organization.id, name, description, agent_id)
        roles_by_name[name] = role
    print(f"Created {len(roles_by_name)} roles")

    print("Created users (email / password):")
    for name, email, password, role_name in USER_DEFINITIONS:
        await user_service.create_user(organization.id, name, email, password, roles_by_name[role_name].id)
        print(f"  {email} / {password}  ({role_name})")

    definition = await workflow_service.create_definition(
        organization.id,
        "Standard Contract Lifecycle",
        "Draft -> Negotiate -> Sign -> Store, with Renew/Amend loops and a Terminate -> Archive -> Destruct tail.",
    )
    for key, name, agent_name, description, is_initial, is_terminal in STEP_DEFINITIONS:
        await workflow_service.add_step(
            definition.id,
            key,
            name,
            agents_by_name[agent_name].id,
            description,
            is_initial,
            is_terminal,
        )
    for from_key, to_key, action_name, description in TRANSITION_DEFINITIONS:
        await workflow_service.add_transition(definition.id, from_key, to_key, action_name, description)
    definition = await workflow_service.activate(definition.id)
    print(f"Created and activated workflow: {definition.name}")

    document = await document_service.create_document(
        organization.id,
        "Vendor Services Agreement",
        "MSA",
        definition.id,
        actor="seed-script",
        description="Sample contract to explore the workflow with.",
    )
    print(f"Created sample document: {document.title} (id={document.id})")

    storage_connection = await storage_service.connect_bucket(
        organization.id,
        StorageProvider.LOCAL,
        display_name="Local disk (dev)",
        config={"prefix": organization.slug},
        credentials={},
    )
    print(f"Connected storage backend: {storage_connection.display_name} ({storage_connection.provider.value})")

    version = await document_service.upload_version(
        document.id,
        file_bytes=b"This is a placeholder contract body for the seeded demo document.\n",
        filename="vendor-services-agreement-v1.txt",
        content_type="text/plain",
        uploaded_by="seed-script",
        notes="Initial draft.",
    )
    print(f"Uploaded version {version.version_no} ({version.size_bytes} bytes) to {version.storage_key}")
    print(f"\nVisit http://127.0.0.1:8000/{organization.slug}/ once the server is running.")


if __name__ == "__main__":
    asyncio.run(main())
