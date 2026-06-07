"""Bidirectional Phoenix MCP integration -- read evidence, write prompts/tags/datasets.

Uses Phoenix Python SDK (phoenix.client.Client) as the primary communication path.
MCP subprocess integration is optional and logs a message if unavailable.

Verified against arize-phoenix-client SDK API (context7, May 2026):
- client.spans.get_spans_dataframe(project_identifier, query)
- client.spans.get_span_annotations_dataframe(spans_dataframe, project_identifier)
- client.prompts.get(prompt_identifier, tag) / .get(prompt_version_id)
- client.prompts.create(name, version=PromptVersion(...))
- client.prompts.tags.create(prompt_version_id, name, description)
- client.datasets.create_dataset(name, dataframe, input_keys, output_keys)
- client.datasets.get_dataset(dataset)
"""

import logging
from collections.abc import Callable
from typing import Protocol

import pandas as pd
from pydantic import BaseModel, Field

from src.config import get_settings
from src.tracing.phoenix_client import get_phoenix_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models for data crossing module boundaries (per CLAUDE.md rules)
# ---------------------------------------------------------------------------


class TraceRecord(BaseModel):
    """A single trace/span record returned from Phoenix."""

    span_id: str | None = None
    trace_id: str | None = None
    name: str | None = None
    status_code: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    latency_ms: float | None = None
    attributes: dict | None = None


class AnnotationRecord(BaseModel):
    """A single annotation record from Phoenix."""

    annotation_name: str | None = None
    annotator_kind: str | None = None
    score: float | None = None
    label: str | None = None
    explanation: str | None = None
    span_id: str | None = None


class PromptInfo(BaseModel):
    """Prompt metadata returned from Phoenix."""

    name: str
    tag: str | None = None
    template: str = ""
    version_id: str | None = None
    model_name: str | None = None


class PromptVersionInfo(BaseModel):
    """Summary of a prompt version."""

    version_id: str | None = None
    template_preview: str = ""
    tags: list[str] = Field(default_factory=list)


class UpsertResult(BaseModel):
    """Result of a prompt upsert operation."""

    name: str
    version_id: str | None = None


class TagResult(BaseModel):
    """Result of tagging a prompt version."""

    version_id: str
    tag: str


class DatasetResult(BaseModel):
    """Result of a dataset write operation."""

    dataset_id: str | None = None
    examples_added: int = 0


# Uses client.experiments.resume_experiment — confirmed against arize-phoenix-client
# 1.x on 2026-06-07. log_evaluations does not exist in this SDK version;
# resume_experiment accepts a task+evaluators closure pair and writes runs+scores
# into an existing experiment shell identified by experiment_id.


class ExperimentResult(BaseModel):
    """Experiment results from Phoenix."""

    experiment_id: str
    status: str | None = None
    metrics: dict = Field(default_factory=dict)


class DatasetExample(BaseModel):
    """A single example in a dataset."""

    example_id: str | None = None
    input: dict = Field(default_factory=dict)
    expected_output: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Protocol for Phoenix client (duck-typing interface per CLAUDE.md)
# ---------------------------------------------------------------------------


class PhoenixClientProtocol(Protocol):
    """Duck-typing protocol for the Phoenix client to enable testing."""

    @property
    def spans(self) -> object: ...

    @property
    def prompts(self) -> object: ...

    @property
    def datasets(self) -> object: ...


# ---------------------------------------------------------------------------
# PhoenixMCPClient
# ---------------------------------------------------------------------------


class PhoenixMCPClient:
    """Client for bidirectional Phoenix operations (read + write).

    Uses the Phoenix Python SDK for all operations. Named "MCP" to reflect
    the architectural intent of bidirectional communication with Phoenix.

    All external SDK calls are wrapped in try/except with logging per
    the project error-handling standards. Methods return typed Pydantic
    models (or lists of them) rather than raw dicts.
    """

    def __init__(self, phoenix_client: PhoenixClientProtocol | None = None) -> None:
        self._client = phoenix_client or get_phoenix_client()
        self._project = get_settings().phoenix_project_name
        if self._client is None:
            logger.warning(
                "Phoenix client unavailable -- MCP operations will be no-ops"
            )
        else:
            logger.info(
                "PhoenixMCPClient initialized (project=%s). "
                "MCP subprocess integration is optional; using SDK directly.",
                self._project,
            )

    # ------------------------------------------------------------------
    # Read Operations
    # ------------------------------------------------------------------

    async def query_traces(self, limit: int = 20) -> list[TraceRecord]:
        """Query recent traces/spans from Phoenix.

        Uses ``client.spans.get_spans_dataframe`` with the configured
        project identifier.
        """
        if self._client is None:
            return []
        try:
            spans_df: pd.DataFrame | None = self._client.spans.get_spans_dataframe(
                project_identifier=self._project,
            )
            if spans_df is None or spans_df.empty:
                return []
            # Limit rows
            spans_df = spans_df.head(limit)
            records: list[TraceRecord] = []
            for _, row in spans_df.iterrows():
                records.append(
                    TraceRecord(
                        span_id=str(row.get("context.span_id", "")),
                        trace_id=str(row.get("context.trace_id", "")),
                        name=str(row.get("name", "")),
                        status_code=str(row.get("status_code", "")),
                        start_time=str(row.get("start_time", "")),
                        end_time=str(row.get("end_time", "")),
                        latency_ms=row.get("latency_ms"),
                        attributes=_safe_row_to_dict(row),
                    )
                )
            return records
        except Exception as exc:
            logger.warning("Failed to query traces: %s", exc)
            return []

    async def query_spans(self, trace_id: str) -> list[TraceRecord]:
        """Get spans for a specific trace using a SpanQuery filter."""
        if self._client is None:
            return []
        try:
            from phoenix.client.types.spans import SpanQuery

            query = SpanQuery().where(f"trace_id == '{trace_id}'")
            spans_df: pd.DataFrame | None = self._client.spans.get_spans_dataframe(
                project_identifier=self._project,
                query=query,
            )
            if spans_df is None or spans_df.empty:
                return []
            records: list[TraceRecord] = []
            for _, row in spans_df.iterrows():
                records.append(
                    TraceRecord(
                        span_id=str(row.get("context.span_id", "")),
                        trace_id=str(row.get("context.trace_id", "")),
                        name=str(row.get("name", "")),
                        status_code=str(row.get("status_code", "")),
                        start_time=str(row.get("start_time", "")),
                        end_time=str(row.get("end_time", "")),
                        latency_ms=row.get("latency_ms"),
                        attributes=_safe_row_to_dict(row),
                    )
                )
            return records
        except ImportError:
            logger.warning(
                "phoenix.client.types.spans not available; cannot filter by trace_id"
            )
            return []
        except Exception as exc:
            logger.warning("Failed to query spans for trace %s: %s", trace_id, exc)
            return []

    async def read_annotations(self, trace_id: str) -> list[AnnotationRecord]:
        """Read annotations for spans in a trace.

        The SDK method ``get_span_annotations_dataframe`` requires a
        ``spans_dataframe`` (not raw span IDs), so we first fetch spans
        then retrieve their annotations.
        """
        if self._client is None:
            return []
        try:
            # Step 1: get spans DataFrame for the trace
            spans_df: pd.DataFrame | None = None
            try:
                from phoenix.client.types.spans import SpanQuery

                query = SpanQuery().where(f"trace_id == '{trace_id}'")
                spans_df = self._client.spans.get_spans_dataframe(
                    project_identifier=self._project,
                    query=query,
                )
            except ImportError:
                spans_df = self._client.spans.get_spans_dataframe(
                    project_identifier=self._project,
                )

            if spans_df is None or spans_df.empty:
                return []

            # Step 2: get annotations for those spans
            annotations_df: pd.DataFrame | None = (
                self._client.spans.get_span_annotations_dataframe(
                    spans_dataframe=spans_df,
                    project_identifier=self._project,
                )
            )
            if annotations_df is None or annotations_df.empty:
                return []

            records: list[AnnotationRecord] = []
            for _, row in annotations_df.iterrows():
                records.append(
                    AnnotationRecord(
                        annotation_name=str(row.get("annotation_name", "")),
                        annotator_kind=str(row.get("annotator_kind", "")),
                        score=row.get("score"),
                        label=str(row.get("label", "")),
                        explanation=str(row.get("explanation", "")),
                        span_id=str(row.get("context.span_id", "")),
                    )
                )
            return records
        except Exception as exc:
            logger.warning(
                "Failed to read annotations for trace %s: %s", trace_id, exc
            )
            return []

    async def read_production_prompt(self) -> PromptInfo | None:
        """Get the current production-tagged prompt."""
        if self._client is None:
            return None
        try:
            prompt = self._client.prompts.get(
                prompt_identifier="support-agent",
                tag="production",
            )
            if prompt is None:
                return None
            return PromptInfo(
                name="support-agent",
                tag="production",
                template=str(getattr(prompt, "_template", "")),
                version_id=str(getattr(prompt, "id", "")),
                model_name=getattr(prompt, "_model_name", None),
            )
        except Exception as exc:
            logger.warning("Failed to read production prompt: %s", exc)
            return None

    async def list_prompt_versions(self) -> list[PromptVersionInfo]:
        """List all prompt versions with tags.

        Note: The Phoenix SDK ``prompts.list`` method may not exist in all
        versions. Falls back gracefully.
        """
        if self._client is None:
            return []
        try:
            versions = self._client.prompts.list(name="support-agent")
            result: list[PromptVersionInfo] = []
            for v in versions:
                template_str = str(getattr(v, "_template", ""))[:200]
                tags_raw = getattr(v, "tags", [])
                tags = [str(t) for t in tags_raw] if tags_raw else []
                result.append(
                    PromptVersionInfo(
                        version_id=str(getattr(v, "id", "")),
                        template_preview=template_str,
                        tags=tags,
                    )
                )
            return result
        except AttributeError:
            logger.warning(
                "prompts.list not available in this Phoenix SDK version"
            )
            return []
        except Exception as exc:
            logger.warning("Failed to list prompt versions: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Write Operations
    # ------------------------------------------------------------------

    async def upsert_prompt(
        self,
        name: str,
        template_messages: list[dict],
        model_name: str = "gemini-2.5-flash",
    ) -> UpsertResult | None:
        """Create or update a prompt version.

        Uses ``PromptVersion`` from ``phoenix.client.types`` to construct
        the version object, as required by the SDK.
        """
        if self._client is None:
            return None
        try:
            from phoenix.client.types import PromptVersion

            version_obj = PromptVersion(
                template_messages,
                model_name=model_name,
            )
            created = self._client.prompts.create(
                name=name,
                version=version_obj,
            )
            version_id = str(getattr(created, "id", ""))
            logger.info("Created prompt version: %s (id=%s)", name, version_id)
            return UpsertResult(name=name, version_id=version_id)
        except ImportError:
            logger.warning(
                "phoenix.client.types.PromptVersion not available; "
                "cannot create prompt version"
            )
            return None
        except Exception as exc:
            logger.warning("Failed to upsert prompt %s: %s", name, exc)
            return None

    async def tag_prompt_version(
        self, prompt_version_id: str, tag_name: str
    ) -> TagResult | None:
        """Tag a prompt version (e.g., 'candidate', 'production').

        SDK signature: ``client.prompts.tags.create(
            prompt_version_id=..., name=..., description=...
        )``
        """
        if self._client is None:
            return None
        try:
            self._client.prompts.tags.create(
                prompt_version_id=prompt_version_id,
                name=tag_name,
                description=f"Tagged by PhoenixLoop as '{tag_name}'",
            )
            logger.info(
                "Tagged prompt version %s as '%s'", prompt_version_id, tag_name
            )
            return TagResult(version_id=prompt_version_id, tag=tag_name)
        except Exception as exc:
            logger.warning("Failed to tag prompt version: %s", exc)
            return None

    async def add_dataset_examples(
        self,
        dataset_name: str,
        examples_df: pd.DataFrame,
        input_keys: list[str],
        output_keys: list[str],
    ) -> DatasetResult | None:
        """Add examples to a Phoenix dataset.

        The SDK ``datasets.create_dataset`` accepts a pandas DataFrame with
        explicit input/output key columns.
        """
        if self._client is None:
            return None
        try:
            dataset = self._client.datasets.create_dataset(
                name=dataset_name,
                dataframe=examples_df,
                input_keys=input_keys,
                output_keys=output_keys,
            )
            dataset_id = str(getattr(dataset, "id", ""))
            num_examples = len(examples_df)
            logger.info(
                "Created/updated dataset '%s' with %d examples (id=%s)",
                dataset_name,
                num_examples,
                dataset_id,
            )
            return DatasetResult(
                dataset_id=dataset_id, examples_added=num_examples
            )
        except Exception as exc:
            logger.warning("Failed to add dataset examples: %s", exc)
            return None

    async def get_dataset(self, dataset_name: str) -> list[DatasetExample]:
        """Retrieve examples from a named dataset.

        SDK signature: ``client.datasets.get_dataset(dataset=name)``
        """
        if self._client is None:
            return []
        try:
            dataset = self._client.datasets.get_dataset(dataset=dataset_name)
            if dataset is None:
                return []
            examples = getattr(dataset, "examples", [])
            return [
                DatasetExample(
                    example_id=str(getattr(e, "id", "")),
                    input=getattr(e, "input", {}),
                    expected_output=getattr(e, "expected_output", {}),
                )
                for e in examples
            ]
        except Exception as exc:
            logger.warning(
                "Failed to get dataset '%s': %s", dataset_name, exc
            )
            return []

    async def read_experiment_results(
        self, experiment_id: str
    ) -> ExperimentResult | None:
        """Get experiment results from Phoenix.

        Note: The SDK primarily exposes ``experiments.run_experiment`` for
        running experiments. Direct retrieval by ID may not be available
        in all versions. Falls back gracefully.
        """
        if self._client is None:
            return None
        try:
            experiment = self._client.experiments.get(
                experiment_id=experiment_id
            )
            if experiment is None:
                return None
            return ExperimentResult(
                experiment_id=experiment_id,
                status=str(getattr(experiment, "status", "")),
                metrics=getattr(experiment, "metrics", {}),
            )
        except AttributeError:
            logger.warning(
                "experiments.get not available in this Phoenix SDK version; "
                "experiment retrieval requires the Phoenix UI or run_experiment API"
            )
            return None
        except Exception as exc:
            logger.warning(
                "Failed to read experiment %s: %s", experiment_id, exc
            )
            return None

    async def log_experiment_runs(
        self,
        *,
        phoenix_experiment_id: str,
        per_example: list[dict],
    ) -> bool:
        """Attach per-example outputs + scores to a Phoenix experiment shell.

        Uses ``client.experiments.resume_experiment`` — the only SDK path that
        writes runs into an existing shell without re-creating the experiment.
        ``log_evaluations`` does not exist in arize-phoenix-client 1.x.

        ``per_example`` rows are shaped:
            {
                "example_id": str,                # Phoenix DatasetExample id (or local stub)
                "input": dict,                    # the input we ran on
                "output": dict,                   # the agent's response
                "evaluations": list[dict],        # [{name, score, label, explanation}]
                "latency_ms": int | None,
            }

        Returns True if the SDK accepted the write, False otherwise. Failure
        is logged WARN and swallowed — Phoenix-side observability gaps must
        never break the local SQLite write path.
        """
        if self._client is None:
            return False
        if not per_example:
            return True
        try:
            import asyncio

            # Build lookup: ticket_id → row (used by the task closure)
            output_by_ticket: dict[str, dict] = {}
            eval_by_ticket: dict[str, list[dict]] = {}
            for row in per_example:
                ticket_id = row.get("input", {}).get("ticket_id") or row.get("example_id", "")
                output_by_ticket[ticket_id] = row.get("output") or {}
                eval_by_ticket[ticket_id] = row.get("evaluations") or []

            def _task(input: dict) -> dict:  # noqa: A002 — name is SDK-mandated
                tid = input.get("ticket_id", "")
                return output_by_ticket.get(tid, {"_no_match": True})

            # Build per-evaluator closures; each returns {score, label, explanation}
            eval_names: set[str] = set()
            for evals in eval_by_ticket.values():
                for e in evals:
                    eval_names.add(e["name"])

            def _make_evaluator(
                eval_name: str,
            ) -> Callable[[dict, dict], dict]:
                def _evaluator(input: dict, output: dict) -> dict:  # noqa: A002
                    tid = input.get("ticket_id", "")
                    for e in eval_by_ticket.get(tid, []):
                        if e["name"] == eval_name:
                            return {
                                "score": e.get("score"),
                                "label": e.get("label"),
                                "explanation": e.get("explanation"),
                            }
                    return {"score": None, "label": "no_data"}

                _evaluator.__name__ = eval_name
                return _evaluator

            evaluators = {name: _make_evaluator(name) for name in sorted(eval_names)}

            def _log() -> bool:
                self._client.experiments.resume_experiment(
                    experiment_id=phoenix_experiment_id,
                    task=_task,
                    evaluators=evaluators if evaluators else None,
                    print_summary=False,
                )
                return True

            return await asyncio.to_thread(_log)
        except AttributeError:
            logger.warning(
                "experiments.resume_experiment not exposed by this Phoenix SDK "
                "version — per-example results stay local only."
            )
            return False
        except Exception as exc:
            logger.warning(
                "Failed to log experiment runs for %s: %s",
                phoenix_experiment_id,
                exc,
            )
            return False


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _safe_row_to_dict(row: pd.Series) -> dict:
    """Convert a pandas Series to a dict, coercing non-serialisable values."""
    result: dict = {}
    for key, value in row.items():
        try:
            # Filter to only include attribute columns to keep payload small
            key_str = str(key)
            if key_str.startswith("attributes.") or key_str.startswith("context."):
                if pd.notna(value):
                    result[key_str] = str(value)
        except (TypeError, ValueError):
            continue
    return result
