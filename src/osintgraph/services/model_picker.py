"""Terminal model selector for capability-filtered catalogs.

Osintgraph is a Rich terminal application, so the provider's "model dropdown"
is a numbered, searchable list rendered from the live OrcaRouter catalog. The
selector never offers free-form model entry: every option comes from the
catalog (or, during an outage, from the explicitly labelled verified fallback),
and the list is rebuilt for the capability the caller asks for.
"""

from __future__ import annotations

from typing import Callable, Iterable, List, Optional, Sequence

from .orcarouter import ModelRecord, describe_model, filter_models


def build_options(
    models: Iterable[ModelRecord], capability: str = "chat"
) -> List[ModelRecord]:
    """Return the options that may be shown for ``capability``."""
    return filter_models(models, capability)


def format_options(
    options: Sequence[ModelRecord], selected: Optional[str] = None, start: int = 1
) -> List[str]:
    lines = []
    for index, model in enumerate(options, start):
        marker = "*" if model.id == selected else " "
        lines.append("{} [{}] {}".format(marker, index, describe_model(model)))
    return lines


def render(
    options: Sequence[ModelRecord],
    capability: str,
    catalog_source: str,
    degraded: bool = False,
    selected: Optional[str] = None,
) -> str:
    header = "OrcaRouter Cyber Inference - {} models ({})".format(capability, catalog_source)
    if degraded:
        header += " [DEGRADED: live catalog unavailable]"
    body = ["", header, ""]
    body.extend(format_options(options, selected=selected))
    body.append("")
    body.append("Enter a number, a model id, a substring to search, or press Enter for the default.")
    return "\n".join(body)


def parse_selection(
    text: str, options: Sequence[ModelRecord], default: Optional[str] = None
) -> Optional[str]:
    """Map user input to a model id.

    Returns ``None`` for cancel, ``""`` to re-prompt (no match), and the
    selected id otherwise. Free-form ids are accepted only when they are one of
    the options, so the selector cannot be bypassed with a guessed string.
    """
    value = (text or "").strip()
    if not value:
        return default if default and any(m.id == default for m in options) else None
    if value.lower() in ("q", "quit", "cancel"):
        return None
    if value.isdigit():
        index = int(value)
        if 1 <= index <= len(options):
            return options[index - 1].id
        return ""
    exact = [m.id for m in options if m.id == value]
    if exact:
        return exact[0]
    matches = [m.id for m in options if value.lower() in m.id.lower()]
    if len(matches) == 1:
        return matches[0]
    return ""


def choose_model(
    models: Iterable[ModelRecord],
    capability: str = "chat",
    catalog_source: str = "live",
    degraded: bool = False,
    selected: Optional[str] = None,
    default: Optional[str] = None,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
    attempts: int = 3,
) -> Optional[str]:
    """Interactively choose a model from the filtered catalog."""
    options = build_options(models, capability)
    if not options:
        write(
            "No {} models are available from OrcaRouter right now. "
            "Nothing has been changed.".format(capability)
        )
        return None
    write(render(options, capability, catalog_source, degraded=degraded, selected=selected))
    pool = options
    attempts_left = max(1, attempts)
    while attempts_left > 0:
        answer = read("Model > ")
        result = parse_selection(answer, pool, default=default)
        if result is None:
            return None
        if result:
            return result
        stripped = (answer or "").strip()
        if stripped and not stripped.isdigit():
            filtered = [m for m in options if stripped.lower() in m.id.lower()]
            if filtered:
                pool = filtered
                write("Matches:")
                for line in format_options(pool):
                    write(line)
                # Searching is not a wrong answer; keep the attempt budget.
                continue
            write("No model matches '{}'.".format(stripped))
        else:
            write("Pick a number between 1 and {}.".format(len(pool)))
        attempts_left -= 1
    return None
