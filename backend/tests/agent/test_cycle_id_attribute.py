"""phoenixloop_cycle_id is included in using_attributes metadata.

Audit P2-8: Phoenix groups spans by ``session_id`` by default. Adding a
custom ``phoenixloop_cycle_id`` attribute to every span we emit during a
healing loop (support_agent -> diagnosis_agent -> experiments ->
release_gate) lets a judge filter all related spans with a single
predicate, even when the underlying ADK sessions differ.
"""

import inspect

from src.agent import diagnosis_agent, support_agent


def test_support_agent_passes_cycle_id_into_using_attributes() -> None:
    """The support_agent module must reference phoenixloop_cycle_id when
    building per-run span attributes. This is required so a judge can group
    spans by healing cycle in Phoenix."""
    src = inspect.getsource(support_agent)
    assert "phoenixloop_cycle_id" in src, (
        "support_agent.py must thread phoenixloop_cycle_id through "
        "using_attributes (P2-8 audit fix)"
    )


def test_diagnosis_agent_passes_cycle_id_into_using_attributes() -> None:
    """The diagnosis_agent module must reference phoenixloop_cycle_id when
    building per-run span attributes — same rationale as support_agent."""
    src = inspect.getsource(diagnosis_agent)
    assert "phoenixloop_cycle_id" in src, (
        "diagnosis_agent.py must thread phoenixloop_cycle_id through "
        "using_attributes (P2-8 audit fix)"
    )


def test_support_agent_entrypoint_accepts_phoenixloop_cycle_id() -> None:
    """``run_agent`` and ``run_agent_events`` must expose an optional
    ``phoenixloop_cycle_id`` keyword so orchestrators can thread the id."""
    for fn in (support_agent.run_agent, support_agent.run_agent_events):
        sig = inspect.signature(fn)
        assert "phoenixloop_cycle_id" in sig.parameters, (
            f"{fn.__name__} must accept phoenixloop_cycle_id keyword"
        )
        param = sig.parameters["phoenixloop_cycle_id"]
        assert param.default is None, (
            f"{fn.__name__}.phoenixloop_cycle_id must default to None so "
            "existing callers stay source-compatible"
        )


def test_diagnosis_agent_entrypoint_accepts_phoenixloop_cycle_id() -> None:
    """``run_diagnosis_agent`` must expose the same optional keyword."""
    sig = inspect.signature(diagnosis_agent.run_diagnosis_agent)
    assert "phoenixloop_cycle_id" in sig.parameters, (
        "run_diagnosis_agent must accept phoenixloop_cycle_id keyword"
    )
    param = sig.parameters["phoenixloop_cycle_id"]
    assert param.default is None, (
        "run_diagnosis_agent.phoenixloop_cycle_id must default to None"
    )
