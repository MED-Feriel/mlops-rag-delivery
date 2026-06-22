"""Tests unitaires du versioning de prompt (C.5)."""

import hashlib

from src.llm.llm_service import PROMPT_SHA, PROMPT_VERSION, SYSTEM_PROMPT


def test_prompt_sha_matches_text():
    expected = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
    assert PROMPT_SHA == expected


def test_prompt_version_is_nonempty_string():
    assert isinstance(PROMPT_VERSION, str) and PROMPT_VERSION.strip()


def test_prompt_sha_is_stable_length():
    assert len(PROMPT_SHA) == 12
