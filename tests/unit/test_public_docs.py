"""Every public callable says what it accepts, what it returns, and shows an example.

"Public" is `sus.__all__`: its functions and the public methods of its classes. The
docstrings are Google style, so the docs site renders a parameter table.

- `Args:` names every parameter; a `Literal` parameter lists every accepted value.
- `Returns:` is present unless the function returns `None`.
- `Examples:` is always present, and every example not marked `# doctest: +SKIP` runs
  here. Offline examples use codes from the packaged dictionaries; the meaning of those
  codes is tested elsewhere on committed DATASUS files.
"""

from __future__ import annotations

import doctest
import inspect
import re
import typing
from collections.abc import Callable, Iterator

import pytest

import omnisus as sus

SECTION = re.compile(r"^(Args|Returns|Yields|Raises|Warns|Examples|Attributes):$")


def _public() -> Iterator[tuple[str, Callable]]:
    seen: set[int] = set()
    for name in sus.__all__:
        obj = getattr(sus, name)
        if inspect.isclass(obj):
            members = [
                (f"{name}.{member}", getattr(value, "__func__", value))
                for member, value in inspect.getmembers(obj)
                if not member.startswith("_")
            ]
        else:
            members = [(name, obj)]
        for qualified, function in members:
            if (
                inspect.isfunction(function)
                and function.__module__.startswith("omnisus")
                and id(function) not in seen
            ):
                seen.add(id(function))
                yield qualified, function


PUBLIC = dict(_public())


def _sections(function: Callable) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in (inspect.getdoc(function) or "").splitlines():
        if SECTION.match(line):
            current = line[:-1]
            sections[current] = []
        elif current is not None and line and not line.startswith(" "):
            current = None
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines) for name, lines in sections.items()}


def _args(text: str) -> dict[str, str]:
    entries: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        match = re.match(r"^    (\*{0,2}\w+)(?: \(.*\))?:", line)
        if match:
            current = match.group(1).lstrip("*")
            entries[current] = [line]
        elif current is not None:
            entries[current].append(line)
    return {name: "\n".join(lines) for name, lines in entries.items()}


def _literal_values(hint: object) -> list[object]:
    """Accepted values of a ``Literal`` hint, also inside ``X | None``."""
    if typing.get_origin(hint) is typing.Literal:
        return list(typing.get_args(hint))
    return [value for arg in typing.get_args(hint) for value in _literal_values(arg)]


def _parameters(function: Callable) -> list[inspect.Parameter]:
    return [
        p for p in inspect.signature(function).parameters.values() if p.name not in ("self", "cls")
    ]


@pytest.mark.parametrize("name", sorted(PUBLIC))
def test_docstring_documents_every_parameter_and_the_result(name: str) -> None:
    function = PUBLIC[name]
    sections = _sections(function)
    parameters = _parameters(function)
    try:
        hints = typing.get_type_hints(function)
    except NameError:  # a name imported only under TYPE_CHECKING
        hints = {k: None if v == "None" else v for k, v in function.__annotations__.items()}

    assert "Examples" in sections, f"{name}: no Examples section"
    if hints.get("return", type(None)) not in (type(None), None):
        assert "Returns" in sections or "Yields" in sections, f"{name}: no Returns section"
    if parameters:
        documented = _args(sections.get("Args", ""))
        missing = [p.name for p in parameters if p.name not in documented]
        assert not missing, f"{name}: Args does not document {missing}"
        for p in parameters:
            for value in _literal_values(hints.get(p.name)):
                forms = (repr(value), f'"{value}"', f"``{value}``")
                assert any(form in documented[p.name] for form in forms), (
                    f"{name}: Args of {p.name} does not list {value!r}"
                )


@pytest.mark.parametrize("name", sorted(PUBLIC))
def test_examples_run(name: str) -> None:
    finder = doctest.DocTestFinder(recurse=False)
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE)
    for test in finder.find(PUBLIC[name], name, globs={}):
        runner.run(test)
    result = runner.summarize(verbose=False)
    assert result.failed == 0, f"{name}: {result.failed} example(s) failed"
