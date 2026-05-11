# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Utilities for source-backed Python function workflows."""

from __future__ import annotations

import ast
import builtins
import textwrap
import types
from typing import Callable


def function_to_source(func: Callable) -> bytes:
    """Serialize a Python function workflow as UTF-8 source bytes."""
    import inspect

    source = textwrap.dedent(inspect.getsource(func))
    validate_self_contained_function_source(source)
    return source.encode("utf-8")


def validate_self_contained_function_source(
    source: bytes | str,
    function_name: str | None = None,
) -> None:
    """Reject function-only source that depends on module globals."""
    source_text = _source_text(source)
    tree = ast.parse(source_text)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    target = None
    if function_name:
        target = next((node for node in functions if node.name == function_name), None)
    elif any(node.name == "simulate" for node in functions):
        target = next(node for node in functions if node.name == "simulate")
    elif len(functions) == 1:
        target = functions[0]
    if target is None:
        return

    locals_seen = _assigned_names(target)
    loaded = {
        node.id
        for node in ast.walk(target)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    allowed = set(dir(builtins)) | {target.name}
    missing = sorted(loaded - locals_seen - allowed)
    if missing:
        raise ValueError(
            "Function workflow source is not self-contained; unresolved names: "
            + ", ".join(missing)
        )


def function_from_source(source: bytes | str, function_name: str | None = None) -> Callable:
    """Load a function workflow from UTF-8 source text.

    The source must define exactly one top-level function unless function_name
    is supplied. This is intentionally source-backed, not pickle-backed, so
    workflow bundles remain inspectable and portable.
    """
    source_text = _source_text(source)

    tree = ast.parse(source_text)
    functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    if function_name is None:
        if "simulate" in functions:
            function_name = "simulate"
        elif len(functions) == 1:
            function_name = functions[0]
        else:
            raise ValueError(
                "Function workflow source must define simulate() or exactly one top-level function"
            )

    module = types.ModuleType("sim2l_source_workflow")
    exec(compile(source_text, "<sim2l-function-workflow>", "exec"), module.__dict__)  # noqa: S102
    func = getattr(module, function_name, None)
    if not callable(func):
        raise ValueError(f"Function workflow source does not define callable {function_name}()")
    func.__sim2l_source__ = source_text
    return func


def _source_text(source: bytes | str) -> str:
    if isinstance(source, bytes):
        source = source.decode("utf-8")
    return textwrap.dedent(source)


def _assigned_names(func_node: ast.FunctionDef) -> set[str]:
    names = {arg.arg for arg in func_node.args.args}
    names.update(arg.arg for arg in func_node.args.kwonlyargs)
    if func_node.args.vararg:
        names.add(func_node.args.vararg.arg)
    if func_node.args.kwarg:
        names.add(func_node.args.kwarg.arg)

    for node in ast.walk(func_node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names
