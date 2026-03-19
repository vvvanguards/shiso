"""LLM-assisted drafting for workflow definitions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.exc import OperationalError

from ..database import SessionLocal
from ..models.tools import ToolRunOutput, WorkflowRevisionSuggestionRecord
from ..tools import Workflow
from .llm import llm_chat

_ALLOWED_FIELD_TYPES = {"str", "float", "int", "bool"}
_ALLOWED_SUGGESTION_STATUSES = {"open", "applied", "dismissed"}

_DRAFT_SYSTEM_PROMPT = """You design workflow definitions for Shiso.

A workflow definition must include:
- key: lowercase snake_case tool key
- name: short human-readable name
- description: one sentence
- prompt_template: browser-agent instructions for what to navigate to and extract
- result_key: plural snake_case field name that holds the extracted items
- output_schema_json: array of field specs

Each field spec must be JSON with:
- name: snake_case field name
- type: one of str, float, int, bool
- nullable: true or false
- default: optional JSON scalar default

Rules:
- Keep prompts concrete and operational, not abstract.
- Prefer compact schemas with primitive fields only.
- Do not include nested objects or arrays in output_schema_json.
- If examples are provided, align the schema to them.
- If revising an existing workflow, keep the same key unless there is a strong reason not to.

Return JSON only.
"""


@dataclass(slots=True)
class WorkflowRevisionSuggestion:
    """Persisted suggestion for revising a workflow definition."""

    id: int | None = None
    tool_key: str = ""
    provider_key: str = ""
    sync_run_id: int | None = None
    status: str = "open"
    trigger_reason: str = ""
    rationale: str | None = None
    suggested_definition: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


async def draft_workflow_definition(
    brief: str,
    *,
    example_items: list[dict[str, Any]] | None = None,
    existing_workflow: Workflow | None = None,
    llm_chat_fn: Callable | None = None,
) -> dict[str, Any] | None:
    """Generate and normalize a workflow definition draft."""
    if llm_chat_fn is None:
        llm_chat_fn = llm_chat

    example_items = [item for item in (example_items or []) if isinstance(item, dict)]
    seeded_from_history = False
    if not example_items and existing_workflow is not None:
        example_items = load_recent_workflow_examples(
            existing_workflow.key,
            result_key=existing_workflow.result_key,
        )
        seeded_from_history = bool(example_items)

    messages = [
        {"role": "system", "content": _DRAFT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_draft_request(
                brief,
                example_items=example_items,
                existing_workflow=existing_workflow,
            ),
        },
    ]

    result = await llm_chat_fn(messages)
    if not result:
        return None
    normalized = normalize_workflow_draft(
        result,
        brief=brief,
        example_items=example_items,
        existing_workflow=existing_workflow,
    )
    if seeded_from_history:
        note = f"Seeded from {len(example_items)} recent item(s) from prior runs."
        rationale = normalized.get("rationale")
        normalized["rationale"] = f"{rationale} {note}".strip() if rationale else note
    return normalized


async def capture_workflow_revision_suggestion(
    provider_key: str,
    *,
    workflow: Workflow | None,
    sync_run_id: int | None = None,
    metrics: dict[str, Any] | None = None,
    results: list[dict[str, Any]] | None = None,
    error: str | None = None,
    log_lines: list[str] | None = None,
    llm_chat_fn: Callable | None = None,
) -> WorkflowRevisionSuggestion | None:
    """Draft and persist a workflow revision suggestion when a run looks weak."""
    trigger_reason = should_suggest_workflow_revision(
        workflow=workflow,
        metrics=metrics,
        results=results,
        error=error,
    )
    if not trigger_reason or workflow is None:
        return None

    brief = _build_revision_brief(
        provider_key,
        workflow=workflow,
        trigger_reason=trigger_reason,
        metrics=metrics or {},
        error=error,
        log_lines=log_lines or [],
    )
    draft = await draft_workflow_definition(
        brief,
        example_items=[item for item in (results or []) if isinstance(item, dict)],
        existing_workflow=workflow,
        llm_chat_fn=llm_chat_fn,
    )
    if not draft:
        return None

    return save_workflow_revision_suggestion(
        workflow.key,
        provider_key,
        suggestion_definition=draft,
        sync_run_id=sync_run_id,
        trigger_reason=trigger_reason,
        metrics=metrics or {},
    )


def normalize_workflow_draft(
    draft: dict[str, Any],
    *,
    brief: str,
    example_items: list[dict[str, Any]] | None = None,
    existing_workflow: Workflow | None = None,
) -> dict[str, Any]:
    """Normalize an LLM-produced workflow draft into a safe shape."""
    example_items = example_items or []

    key = _snake_case(
        draft.get("key")
        or (existing_workflow.key if existing_workflow else "")
        or draft.get("name")
        or brief
    )
    if not key:
        key = "custom_tool"

    name = str(draft.get("name") or _title_case(key)).strip()
    description = str(draft.get("description") or brief).strip()
    prompt_template = str(
        draft.get("prompt_template")
        or (existing_workflow.prompt_template if existing_workflow else "")
        or f"Navigate to the relevant page and extract the required data for {name}."
    ).strip()
    result_key = _snake_case(draft.get("result_key") or (existing_workflow.result_key if existing_workflow else "items"))
    if not result_key:
        result_key = "items"

    schema = _normalize_schema_specs(draft.get("output_schema_json"))
    if not schema and example_items:
        schema = _infer_schema_from_examples(example_items)
    if not schema and existing_workflow and existing_workflow.schema_spec:
        schema = _normalize_schema_specs(existing_workflow.schema_spec)
    if not schema:
        schema = [{"name": "value", "type": "str", "nullable": False}]

    normalized = {
        "key": key,
        "name": name,
        "description": description,
        "prompt_template": prompt_template,
        "result_key": result_key,
        "output_schema_json": schema,
        "rationale": str(draft.get("rationale") or "").strip() or None,
    }
    return normalized


def _build_draft_request(
    brief: str,
    *,
    example_items: list[dict[str, Any]],
    existing_workflow: Workflow | None,
) -> str:
    existing_payload = None
    if existing_workflow:
        existing_payload = {
            "key": existing_workflow.key,
            "name": existing_workflow.name,
            "description": existing_workflow.description,
            "prompt_template": existing_workflow.prompt_template,
            "result_key": existing_workflow.result_key,
            "output_schema_json": existing_workflow.schema_spec or [],
        }

    return (
        f"WORKFLOW BRIEF:\n{brief.strip()}\n\n"
        f"EXAMPLE ITEMS:\n{json.dumps(example_items, indent=2) if example_items else 'None'}\n\n"
        f"EXISTING WORKFLOW:\n{json.dumps(existing_payload, indent=2) if existing_payload else 'None'}\n\n"
        "Draft a workflow definition."
    )


def should_suggest_workflow_revision(
    *,
    workflow: Workflow | None,
    metrics: dict[str, Any] | None = None,
    results: list[dict[str, Any]] | None = None,
    error: str | None = None,
) -> str | None:
    """Return a human-readable trigger reason when a workflow run looks weak."""
    if workflow is None or workflow.key == "financial_scraper":
        return None

    metrics = metrics or {}
    results_count = len(results or [])
    errors = [str(item).strip() for item in (metrics.get("errors") or []) if str(item).strip()]
    failed_actions = int(metrics.get("failed_actions") or 0)
    steps_taken = int(metrics.get("steps_taken") or 0)
    reasons: list[str] = []

    if error:
        reasons.append(f"Run failed: {error}")
    if metrics.get("timed_out"):
        reasons.append("Run timed out")
    if errors:
        reasons.append(f"{len(errors)} scraper error(s)")
    if results_count == 0:
        reasons.append("No items were extracted")
    if failed_actions >= 3:
        reasons.append(f"{failed_actions} failed actions")
    if steps_taken >= 25 and results_count <= 1:
        reasons.append(f"High step count for low output ({steps_taken} steps)")

    severe = bool(error or metrics.get("timed_out") or errors or failed_actions >= 3)
    weak = results_count == 0 or (results_count <= 1 and failed_actions >= 2) or (steps_taken >= 25 and results_count <= 1)
    if not reasons or not (severe or weak):
        return None

    ordered_reasons = list(dict.fromkeys(reasons))
    return "; ".join(ordered_reasons)


def load_recent_workflow_examples(
    tool_key: str,
    *,
    result_key: str = "items",
    run_limit: int = 5,
    max_items: int = 25,
) -> list[dict[str, Any]]:
    """Load recent extracted items for a workflow to seed draft generation."""
    try:
        with SessionLocal() as session:
            runs = (
                session.query(ToolRunOutput)
                .filter(ToolRunOutput.tool_key == tool_key)
                .order_by(ToolRunOutput.created_at.desc(), ToolRunOutput.id.desc())
                .limit(max(1, min(run_limit, 25)))
                .all()
            )
    except Exception:
        return []

    examples: list[dict[str, Any]] = []
    for run in runs:
        for item in _extract_items_from_output(run.output_json, result_key=result_key):
            if isinstance(item, dict):
                examples.append(item)
            if len(examples) >= max_items:
                return examples
    return examples


def save_workflow_revision_suggestion(
    tool_key: str,
    provider_key: str,
    *,
    suggestion_definition: dict[str, Any],
    sync_run_id: int | None = None,
    trigger_reason: str = "",
    metrics: dict[str, Any] | None = None,
) -> WorkflowRevisionSuggestion | None:
    """Persist or update the open suggestion for a tool/provider pair."""
    try:
        with SessionLocal() as session:
            row = (
                session.query(WorkflowRevisionSuggestionRecord)
                .filter(WorkflowRevisionSuggestionRecord.tool_key == tool_key)
                .filter(WorkflowRevisionSuggestionRecord.provider_key == provider_key)
                .filter(WorkflowRevisionSuggestionRecord.status == "open")
                .order_by(WorkflowRevisionSuggestionRecord.updated_at.desc(), WorkflowRevisionSuggestionRecord.id.desc())
                .first()
            )
            if row is None:
                row = WorkflowRevisionSuggestionRecord(
                    tool_key=tool_key,
                    provider_key=provider_key,
                )
                session.add(row)

            row.sync_run_id = sync_run_id
            row.status = "open"
            row.trigger_reason = str(trigger_reason or "").strip()
            row.rationale = str(suggestion_definition.get("rationale") or "").strip()
            row.suggested_definition_json = dict(suggestion_definition)
            row.metrics_json = dict(metrics or {})
            session.commit()
            session.refresh(row)
            return _workflow_revision_suggestion_from_record(row)
    except (OperationalError, AttributeError):
        return None


def list_workflow_revision_suggestions(
    *,
    status: str | None = "open",
    tool_key: str | None = None,
) -> list[WorkflowRevisionSuggestion]:
    """List persisted workflow revision suggestions."""
    try:
        with SessionLocal() as session:
            query = session.query(WorkflowRevisionSuggestionRecord)
            if status:
                query = query.filter(WorkflowRevisionSuggestionRecord.status == status)
            if tool_key:
                query = query.filter(WorkflowRevisionSuggestionRecord.tool_key == tool_key)
            rows = (
                query.order_by(
                    WorkflowRevisionSuggestionRecord.updated_at.desc(),
                    WorkflowRevisionSuggestionRecord.id.desc(),
                )
                .all()
            )
            return [_workflow_revision_suggestion_from_record(row) for row in rows]
    except (OperationalError, AttributeError):
        return []


def update_workflow_revision_suggestion_status(
    suggestion_id: int,
    status: str,
) -> WorkflowRevisionSuggestion | None:
    """Update a workflow revision suggestion status."""
    status = str(status or "").strip().lower()
    if status not in _ALLOWED_SUGGESTION_STATUSES:
        raise ValueError(f"Unsupported workflow suggestion status: {status}")

    try:
        with SessionLocal() as session:
            row = session.get(WorkflowRevisionSuggestionRecord, suggestion_id)
            if row is None:
                return None
            row.status = status
            session.commit()
            session.refresh(row)
            return _workflow_revision_suggestion_from_record(row)
    except (OperationalError, AttributeError):
        return None


def _normalize_schema_specs(raw_schema: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_schema, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in raw_schema:
        if not isinstance(item, dict):
            continue
        name = _snake_case(item.get("name"))
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        type_name = str(item.get("type") or "str").strip().lower()
        if type_name not in _ALLOWED_FIELD_TYPES:
            type_name = _infer_type_from_value(item.get("default")) or "str"

        normalized_item = {
            "name": name,
            "type": type_name,
            "nullable": bool(item.get("nullable", False)),
        }

        if "default" in item and _is_scalar_json_value(item.get("default")):
            normalized_item["default"] = item["default"]

        normalized.append(normalized_item)
    return normalized


def _infer_schema_from_examples(example_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    field_values: dict[str, list[Any]] = {}
    for item in example_items:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            normalized_key = _snake_case(key)
            if not normalized_key:
                continue
            field_values.setdefault(normalized_key, []).append(value)

    schema: list[dict[str, Any]] = []
    for field_name, values in field_values.items():
        non_null = [value for value in values if value is not None]
        sample = non_null[0] if non_null else None
        type_name = _infer_type_from_value(sample) or "str"
        schema.append(
            {
                "name": field_name,
                "type": type_name,
                "nullable": len(non_null) != len(values) or not non_null,
            }
        )
    return schema


def _infer_type_from_value(value: Any) -> str | None:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    return None


def _snake_case(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = text.strip("_").lower()
    return re.sub(r"_+", "_", text)


def _title_case(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split("_") if part)


def _is_scalar_json_value(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _extract_items_from_output(output_json: Any, *, result_key: str) -> list[Any]:
    if isinstance(output_json, list):
        return output_json

    if not isinstance(output_json, dict):
        return []

    if isinstance(output_json.get(result_key), list):
        return output_json[result_key]

    list_values = [value for value in output_json.values() if isinstance(value, list)]
    if len(list_values) == 1:
        return list_values[0]

    return []


def _build_revision_brief(
    provider_key: str,
    *,
    workflow: Workflow,
    trigger_reason: str,
    metrics: dict[str, Any],
    error: str | None,
    log_lines: list[str],
) -> str:
    parts = [
        f"Revise the {workflow.name} workflow ({workflow.key}) for provider {provider_key}.",
        "Keep the same key unless there is a strong reason to change it.",
        f"Trigger reason: {trigger_reason}.",
    ]
    if error:
        parts.append(f"Top-level run error: {error}.")
    if metrics:
        parts.append(f"Latest run metrics:\n{json.dumps(metrics, indent=2, sort_keys=True)}")

    excerpt = _log_excerpt(log_lines)
    if excerpt:
        parts.append(f"Recent log excerpt:\n{excerpt}")

    parts.append("Revise the prompt and schema only as much as needed to improve reliability and extraction quality.")
    return "\n\n".join(parts)


def _log_excerpt(log_lines: list[str], *, max_lines: int = 12) -> str:
    if not log_lines:
        return ""
    return "\n".join(str(line) for line in log_lines[-max_lines:])


def _workflow_revision_suggestion_from_record(
    row: WorkflowRevisionSuggestionRecord,
) -> WorkflowRevisionSuggestion:
    return WorkflowRevisionSuggestion(
        id=row.id,
        tool_key=row.tool_key,
        provider_key=row.provider_key,
        sync_run_id=row.sync_run_id,
        status=row.status,
        trigger_reason=row.trigger_reason,
        rationale=row.rationale or None,
        suggested_definition=dict(row.suggested_definition_json or {}),
        metrics=dict(row.metrics_json or {}),
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )
