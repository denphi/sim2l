"""Tests for the keyword-OR catalog search recall (A).

The old search matched the whole query as one ``name LIKE %phrase%``, so a
multi-keyword goal essentially never hit. The new recall tokenizes the query
and OR-matches each token across name + description + tags, ranking rows by
how many keywords they match. These tests exercise that directly against the
SQLite backend.
"""

import os
import tempfile

import pytest

from sim2l.services.catalog_service import (
    SQLiteCatalogBackend,
    _keyword_search_sql,
    _search_tokens,
)


def _register(backend, name, description, version="0.1.0", tags=None):
    payload = {
        "name": name,
        "version": version,
        "description": description,
        "workflow_type": "function",
        "workflow_hash": f"hash-{name}",
        "input_schema": {"x": {"type": "Number"}},
        "output_schema": {"y": {"type": "Number"}},
        "tags": tags or [],
    }
    result, status = backend.register_simulation(payload, "no-auth-session")
    assert status in (200, 201), result
    return result


@pytest.fixture()
def backend():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    be = SQLiteCatalogBackend(db_path=path, no_auth=True)
    yield be
    try:
        os.unlink(path)
    except OSError:
        pass


def test_search_tokens_drops_stopwords_and_dups():
    assert _search_tokens("Band Gap band a") == ["band", "gap"]
    assert _search_tokens("") == []
    assert _search_tokens(None) == []


def test_keyword_sql_shapes_params_per_column():
    where, order, params = _keyword_search_sql(["band", "gap"], "LIKE", "?")
    assert where and order
    # 2 tokens x 3 columns (name, description, tags) = 6 params.
    assert len(params) == 6
    assert params == ["%band%"] * 3 + ["%gap%"] * 3


def test_recall_matches_description_not_just_name(backend):
    # Name has nothing to do with "band gap"; description does.
    _register(backend, "sim_alpha", "Predicts the electronic band gap via DFT")
    results, status = backend.search("band gap prediction", None, "active", 10)
    assert status == 200
    names = [r["name"] for r in results]
    assert "sim_alpha" in names


def test_recall_ranks_by_match_count(backend):
    _register(backend, "one_match", "mentions band only")
    _register(backend, "two_match", "covers band and gap together")
    results, _ = backend.search("band gap", None, "active", 10)
    names = [r["name"] for r in results]
    # The row matching both keywords must rank ahead of the single-keyword row.
    assert names.index("two_match") < names.index("one_match")


def test_recall_matches_tags(backend):
    _register(backend, "tagged_sim", "no keywords here", tags=["thermoelectric"])
    results, _ = backend.search("thermoelectric", None, "active", 10)
    assert "tagged_sim" in [r["name"] for r in results]


def test_no_query_returns_all_active(backend):
    _register(backend, "s1", "first")
    _register(backend, "s2", "second")
    results, _ = backend.search(None, None, "active", 10)
    assert len(results) == 2


def test_unrelated_query_returns_nothing(backend):
    _register(backend, "s1", "electronic band gap")
    results, _ = backend.search("quantum chromodynamics lattice", None, "active", 10)
    assert results == []
