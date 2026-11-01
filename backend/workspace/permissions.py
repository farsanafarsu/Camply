"""Role-based permissions. This matrix is the single source of truth for access checks.

Views enforce it on the server with `workspace.decorators.require_perm`; templates use the
`{% can %}` tag only to hide controls a user could not use anyway.
"""

from .models import Role

# (code, label, group) — order here is the order of rows on the Team page.
PERMISSIONS = [
    ("dashboard.view", "View dashboard", "Overview"),
    ("campaigns.view", "View campaigns", "Campaigns"),
    ("campaigns.create", "Create campaigns", "Campaigns"),
    ("campaigns.edit", "Edit, pause and resume campaigns", "Campaigns"),
    ("campaigns.approve", "Approve campaigns", "Campaigns"),
    ("reports.view", "View reports", "Reports"),
    ("reports.export", "Export reports", "Reports"),
    ("creatives.view", "View creatives", "Creatives"),
    ("creatives.edit", "Upload and edit creatives", "Creatives"),
    ("creatives.approve", "Approve creatives", "Creatives"),
    ("leads.view", "View leads", "Leads"),
    ("leads.manage", "Manage leads", "Leads"),
    ("budget.view", "View budgets and wallet ledger", "Budget & wallet"),
    ("budget.manage", "Record ledger entries and invoices", "Budget & wallet"),
    ("billing.manage", "Manage Camply subscription and payments", "Budget & wallet"),
    ("automation.manage", "Manage automation rules", "Automation"),
    ("copilot.use", "Use AI Copilot", "AI Copilot"),
    ("accounts.view", "View ad accounts and connection health", "Integrations"),
    ("integrations.manage", "Connect ad accounts and run syncs", "Integrations"),
    ("clients.manage", "Create and edit clients", "Workspace"),
    ("team.manage", "Invite people and change roles", "Workspace"),
    ("org.manage", "Organization settings", "Workspace"),
    ("audit.view", "View audit log", "Workspace"),
]
ALL_PERMISSIONS = frozenset(code for code, _, _ in PERMISSIONS)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.OWNER: ALL_PERMISSIONS,
    Role.ADMIN: ALL_PERMISSIONS - {"billing.manage", "org.manage"},
    Role.CAMPAIGN_MANAGER: frozenset({
        "dashboard.view", "campaigns.view", "campaigns.create", "campaigns.edit",
        "reports.view", "reports.export", "creatives.view", "creatives.edit",
        "leads.view", "leads.manage", "budget.view", "automation.manage", "copilot.use", "accounts.view",
    }),
    Role.ANALYST: frozenset({
        "dashboard.view", "campaigns.view", "reports.view", "reports.export",
        "creatives.view", "leads.view", "copilot.use", "accounts.view",
    }),
    Role.FINANCE: frozenset({
        "dashboard.view", "reports.view", "reports.export", "budget.view", "budget.manage", "billing.manage",
    }),
    Role.CLIENT: frozenset({
        "dashboard.view", "campaigns.view", "campaigns.approve", "reports.view", "reports.export",
        "creatives.view", "creatives.approve",
    }),
    Role.VIEWER: frozenset({"dashboard.view", "campaigns.view", "reports.view", "creatives.view"}),
}

# Roles a given role may assign when inviting or editing members.
ASSIGNABLE_ROLES = {
    Role.OWNER: [r for r in Role],
    Role.ADMIN: [r for r in Role if r != Role.OWNER],
}


def role_permissions(role) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_perm(membership, perm: str) -> bool:
    if membership is None:
        return False
    if perm not in ALL_PERMISSIONS:
        raise ValueError(f"Unknown permission: {perm}")
    return perm in role_permissions(membership.role)


def permission_matrix():
    """Rows for the Team page: [(group, label, [bool per role])]."""
    roles = list(Role)
    return roles, [
        (group, label, [code in role_permissions(role) for role in roles]) for code, label, group in PERMISSIONS
    ]
