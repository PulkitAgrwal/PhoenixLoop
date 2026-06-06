"""Tests for prompt versioning: models, DB helpers, and the seed at init_db."""

import asyncio
import os
import tempfile

import pytest
from pydantic import ValidationError
from src.db import (
    get_db,
    get_prompt,
    get_prompt_version,
    init_db,
    insert_prompt,
    insert_prompt_version,
    list_prompt_versions,
    set_active_version,
)
from src.models import Prompt, PromptSource, PromptVersion

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

def test_prompt_source_enum_values():
    assert PromptSource.SEED.value == "seed"
    assert PromptSource.DIAGNOSIS_PROPOSAL.value == "diagnosis_proposal"
    assert PromptSource.MANUAL.value == "manual"


def test_prompt_version_requires_non_empty_text():
    with pytest.raises(ValidationError):
        PromptVersion(
            prompt_version_id="v1",
            prompt_identifier="support-agent",
            version_tag="v1.0.0",
            prompt_text="",
            source=PromptSource.SEED,
            created_at="2026-06-06T00:00:00Z",
        )


def test_prompt_version_rejects_oversize_text():
    huge = "x" * 200_001
    with pytest.raises(ValidationError):
        PromptVersion(
            prompt_version_id="v1",
            prompt_identifier="support-agent",
            version_tag="v1.0.0",
            prompt_text=huge,
            source=PromptSource.SEED,
            created_at="2026-06-06T00:00:00Z",
        )


def test_prompt_version_accepts_valid_input():
    pv = PromptVersion(
        prompt_version_id="abc",
        prompt_identifier="support-agent",
        version_tag="v1.0.0",
        prompt_text="You are a helpful agent.",
        parent_version_id=None,
        source=PromptSource.SEED,
        improvement_trigger_id=None,
        created_at="2026-06-06T00:00:00Z",
        metadata_json={"hint": "seed"},
    )
    assert pv.source == PromptSource.SEED
    assert pv.metadata_json == {"hint": "seed"}


def test_prompt_model_optional_fields():
    p = Prompt(
        prompt_identifier="support-agent",
        description=None,
        active_version_id=None,
        created_at="2026-06-06T00:00:00Z",
        updated_at="2026-06-06T00:00:00Z",
    )
    assert p.active_version_id is None


# ---------------------------------------------------------------------------
# DB-helper tests
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    asyncio.run(init_db(path))
    yield path
    for p in (path, path + "-wal", path + "-shm"):
        try:
            os.unlink(p)
        except FileNotFoundError:
            continue


def test_insert_and_get_prompt(db_path):
    async def run():
        async with get_db(db_path) as db:
            await insert_prompt(db, Prompt(
                prompt_identifier="test-prompt",
                description="test",
                active_version_id=None,
                created_at="2026-06-06T00:00:00Z",
                updated_at="2026-06-06T00:00:00Z",
            ))
            fetched = await get_prompt(db, "test-prompt")
            assert fetched is not None
            assert fetched.description == "test"
    asyncio.run(run())


def test_insert_and_list_prompt_versions(db_path):
    async def run():
        async with get_db(db_path) as db:
            await insert_prompt(db, Prompt(
                prompt_identifier="another-prompt",
                description=None,
                active_version_id=None,
                created_at="2026-06-06T00:00:00Z",
                updated_at="2026-06-06T00:00:00Z",
            ))
            pv = PromptVersion(
                prompt_version_id="v-abc",
                prompt_identifier="another-prompt",
                version_tag="v1.0.0",
                prompt_text="Hello.",
                source=PromptSource.SEED,
                created_at="2026-06-06T00:00:00Z",
            )
            await insert_prompt_version(db, pv)
            versions = await list_prompt_versions(db, "another-prompt")
            assert len(versions) == 1
            assert versions[0].prompt_version_id == "v-abc"
            single = await get_prompt_version(db, "v-abc")
            assert single is not None and single.version_tag == "v1.0.0"
    asyncio.run(run())


def test_set_active_version_updates_pointer(db_path):
    async def run():
        async with get_db(db_path) as db:
            await insert_prompt(db, Prompt(
                prompt_identifier="active-test",
                description=None,
                active_version_id=None,
                created_at="2026-06-06T00:00:00Z",
                updated_at="2026-06-06T00:00:00Z",
            ))
            await insert_prompt_version(db, PromptVersion(
                prompt_version_id="v-1",
                prompt_identifier="active-test",
                version_tag="v1.0.0",
                prompt_text="Hello.",
                source=PromptSource.SEED,
                created_at="2026-06-06T00:00:00Z",
            ))
            await set_active_version(db, "active-test", "v-1")
            p = await get_prompt(db, "active-test")
            assert p is not None and p.active_version_id == "v-1"
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Seed tests
# ---------------------------------------------------------------------------

def test_init_db_seeds_default_prompt(db_path):
    """Fresh DB after init_db has the support-agent prompt seeded."""
    async def run():
        async with get_db(db_path) as db:
            p = await get_prompt(db, "support-agent")
            assert p is not None, "prompt row should be seeded"
            assert p.active_version_id is not None, "active version should be set"
            versions = await list_prompt_versions(db, "support-agent")
            assert len(versions) == 1
            assert versions[0].source == PromptSource.SEED
            assert len(versions[0].prompt_text) > 100
    asyncio.run(run())


def test_init_db_seed_is_idempotent(db_path):
    """Calling init_db twice doesn't duplicate the seed."""
    async def run():
        await init_db(db_path)  # second init on same path
        async with get_db(db_path) as db:
            versions = await list_prompt_versions(db, "support-agent")
            assert len(versions) == 1
    asyncio.run(run())
