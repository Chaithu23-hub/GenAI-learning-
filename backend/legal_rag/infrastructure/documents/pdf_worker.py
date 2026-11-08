"""Private subprocess entrypoint: bounded input/output, no filesystem writes."""

from __future__ import annotations

import io
import json
import logging
import sys

from legal_rag.infrastructure.documents.process_limits import restrict_memory


def main() -> int:
    max_pages, max_characters, memory_mb, max_input_bytes = map(int, sys.argv[1:])
    try:
        # Apply the OS cap before importing the parser or reading attacker-controlled input.
        job_handle = restrict_memory(memory_mb)
        logging.disable(logging.CRITICAL)
        from pypdf import PdfReader

        data = sys.stdin.buffer.read(max_input_bytes + 1)
        if len(data) > max_input_bytes:
            raise ValueError("PDF input limit exceeded.")
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > max_pages:
            raise ValueError("PDF page limit exceeded.")
        pages = []
        size = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            size += len(text) + (2 if pages else 0)
            if size > max_characters:
                raise ValueError("PDF output limit exceeded.")
            pages.append(text)
        output = {"text": "\n\n".join(pages).strip()}
        del job_handle  # Windows handle stays open until process exit.
    except Exception as exc:  # noqa: BLE001 — only safe, bounded messages cross this boundary.
        message = (
            str(exc)
            if isinstance(exc, ValueError)
            else "Invalid PDF or processing budget exceeded."
        )
        sys.stdout.buffer.write(json.dumps({"error": message[:200]}).encode("utf-8"))
        return 1
    sys.stdout.buffer.write(json.dumps(output).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
