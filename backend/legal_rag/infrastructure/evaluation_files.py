"""Local evaluation I/O isolated from application workflows."""

from pathlib import Path

from legal_rag.infrastructure.errors import DocumentSourceError


class FilesystemEvaluationFiles:
    def __init__(self, labels_path: Path, artifact_dir: Path):
        self._labels_path = labels_path
        self._artifact_dir = artifact_dir

    def read_labels(self) -> bytes:
        try:
            return self._labels_path.read_bytes()
        except OSError:
            raise DocumentSourceError("Unable to read configured evaluation labels.") from None

    def write_artifact(self, name: str, text: str) -> None:
        if not name or Path(name).name != name or name in {".", ".."}:
            raise DocumentSourceError("Evaluation artifact name must be a filename.")
        try:
            self._artifact_dir.mkdir(parents=True, exist_ok=True)
            (self._artifact_dir / name).write_text(text, encoding="utf-8")
        except OSError:
            raise DocumentSourceError("Unable to write evaluation artifact.") from None
