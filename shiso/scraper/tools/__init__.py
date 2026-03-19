"""Shiso workflow registry — auto-registers built-in workflows on import."""

from .workflows import (
    Workflow,
    delete_workflow_definition,
    get_workflow,
    list_workflows,
    register,
    save_workflow_definition,
    # Schemas re-exported for convenience
    AccountOutput,
    AccountListOutput,
    TenantLead,
    TenantLeadList,
)

__all__ = [
    "Workflow",
    "save_workflow_definition",
    "delete_workflow_definition",
    "get_workflow",
    "list_workflows",
    "register",
    "AccountOutput",
    "AccountListOutput",
    "TenantLead",
    "TenantLeadList",
]
