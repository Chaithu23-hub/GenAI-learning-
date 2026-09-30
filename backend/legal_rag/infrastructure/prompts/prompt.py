"""Prompt template primitive: name + version + text + metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PromptTemplate:
    """A versioned, immutable prompt. `render(**vars)` fills placeholders."""

    name: str
    version: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def render(self, **variables: Any) -> str:
        try:
            return self.text.format(**variables)
        except KeyError as exc:
            raise KeyError(
                f"prompt '{self.name}@{self.version}' missing variable: {exc}"
            ) from exc

    @property
    def id(self) -> str:
        return f"{self.name}@{self.version}"
