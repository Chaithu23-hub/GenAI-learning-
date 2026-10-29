# Repository maintenance

## Production tree

Keep application source, tests/fakes, required evaluation datasets, sample documents, build/deployment files, CI, and current operational documentation in this tree. Preserve working API, CLI, agent, judge, and MCP features when removing unused supporting files.

Generated outputs belong in ignored directories: `frontend/dist/`, `.angular/`, caches, `backend/data/chroma/`, and `backend/data/evaluation/generated/`. Installed dependencies (`node_modules`, virtual environments) are local tooling and are not application source. Credentials stay in ignored `.env` files.

## Archive from 2026-10-29

The full pre-cleanup source snapshot is on the local Git branch:

```text
archive/pre-production-cleanup-2026-10-29
```

Snapshot commit: `6eee37dcf0782be958d1be4fcd65597b6b89ee3a`.

A second local archive contains the moved files at:

```text
D:\GenAI-learning-archive\2026-10-29-production-cleanup
```

Its `manifest.csv` records original and archive paths. It includes historical evaluation reports, weekly learning artifacts, the obsolete deployment walkthrough/backlog, a test-output dump, unused badge/source-card components, the previous production environment module, and the original Angular starter test. The new Angular tests cover the current chat UI. No credentials, model caches, or vector index files were moved.

Required judge/race labels were retained as `backend/data/evaluation/labels.json`. Runtime paths now come from Settings and generated reports have a dedicated ignored output directory. The historical dataset is retained for compatibility; it includes legacy non-contract examples and should be reviewed before using its scores to make production quality claims.

The archive branch is local until explicitly pushed. Inspect archived content with:

```powershell
git ls-tree -r --name-only archive/pre-production-cleanup-2026-10-29
git show archive/pre-production-cleanup-2026-10-29:eval/labels_25.json
```

Do not switch the current working tree to the archive branch while it contains uncommitted work. Use `git show` for inspection or create a separate worktree.
