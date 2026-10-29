# Agent instructions

For paper-reading requests, read SKILL.md and choose quick, guided, or application mode from the user's intent. Read only the relevant reference sections. All modes must distinguish evidence from inference and cover the key experimental limitation.

For repository development:
- Preserve upstream MIT attribution and keep Chinese and English usage documentation consistent.
- Python 3.10+; runtime dependency is PyMuPDF. Do not execute downloaded paper repositories.
- Run `python -m unittest discover -s tests -v` after script changes.
- Keep test fixtures synthetic and offline; live network checks are separate and optional.
- Never commit personal profiles, reading outputs, credentials, downloaded papers, or cloned third-party code.
- Version is in VERSION and scripts/common.py; keep them aligned.
