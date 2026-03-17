"""Shiso workflow registry — auto-registers built-in workflows on import."""

from .workflows import (
    Workflow,
    get_workflow,
    list_workflows,
    register,
    # Schemas re-exported for convenience
    AccountOutput,
    AccountListOutput,
    TenantLead,
    TenantLeadList,
)

__all__ = [
    "Workflow",
    "get_workflow",
    "list_workflows",
    "register",
    "AccountOutput",
    "AccountListOutput",
    "TenantLead",
    "TenantLeadList",
]
