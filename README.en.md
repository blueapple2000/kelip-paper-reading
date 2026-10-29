# kelip-paper-reading · v0.2.0

[简体中文](README.md) · [Release notes](CHANGELOG.md)

Read and critically assess a paper through its original figures, equations, examples and implementation. Choose **quick assessment**, **guided reading**, or **project application**. Every mode addresses the central experimental evidence and its limitations. Respect requests to skip sections or receive one complete answer.

Enhanced derivative of [skJack/kelip-paper-reading](https://github.com/skJack/kelip-paper-reading), based on uploaded snapshot `925953b15813f18b25eeb1a1dca9790f54a47498`. The upstream MIT notice is preserved. This is not an upstream release or endorsement.

## Setup

Python **3.10+**, PyMuPDF, and optional Git. Access to this private repository requires existing GitHub authorization.

```bash
git clone https://github.com/blueapple2000/kelip-paper-reading.git
cd kelip-paper-reading
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Install the directory according to your agent host's local-skill instructions, or ask the agent to read `SKILL.md`. No agent configuration is changed automatically. Workflow and reference instructions are primarily Chinese; the skill instructs the agent to answer in the user's language.

## Prepare materials

```bash
python scripts/fetch_paper.py 2410.24164v1 --dest ./papers/example-v1 --level quick
python scripts/fetch_paper.py ./papers/example-v1 --level full
python scripts/fetch_paper.py ./input.pdf --dest ./papers/local --offline
python scripts/fetch_paper.py ./papers/example-v1 --code https://github.com/owner/repo
```

`quick` retrieves PDF/text/outline without prefetching source, figures or code candidates. `full` prepares additional materials. `--offline` disables all network access and cloning. `--no-clone` records a selected repository without downloading it. `--code` accepts a GitHub HTTPS repository root selected after checking authorship; discovery scores never prove official ownership.

One directory holds one paper version. Resume by passing its directory; use a new destination for another version. The manifest records PDF/source hashes, version verification, code candidates, selected repository and commit. Existing code is not automatically updated. Missing or mismatched source provenance is marked explicitly. Modified PDFs or tracked sources are rejected rather than silently relabeled. Independent figure extraction also checks the PDF hash.

Nonempty code directories must be valid repositories with the expected origin. User files are never cleared. Archive extraction and TeX inclusion are confined to the source directory; network and extraction sizes are bounded. Downloaded repository scripts are not executed.

## Figures and notes

```bash
python scripts/extract_figures.py ./papers/example-v1
python scripts/crop.py ./papers/example-v1/paper.pdf --page 3 --grid
python scripts/crop.py ./papers/example-v1/paper.pdf --page 3 0.1 0.1 0.9 0.6 -o ./papers/example-v1/figures/fig-01.png
```

The figure index includes page/caption/bounding-box information. Manual corrections are preserved using flags or content hashes. Legacy images without recorded hashes are preserved conservatively. Back up and explicitly move a particular image if regeneration is intended. User-curated figure directories are not claimed or overwritten.

The agent maintains reading notes, an evidence table and `reading-state.json` using the templates. Scripts only prepare source materials; they do not call an LLM or produce research conclusions. Store personal preferences in host memory or a user-selected private location, not the shared skill directory.

## Validation and limits

```bash
python -m unittest discover -s tests -v
```

Offline tests use synthetic PDFs, archives, repositories and mocked network responses. CI is configured for Python 3.10, 3.12 and 3.13; local validation uses Python 3.12 / PyMuPDF 1.26.6. A configured CI matrix is not evidence that every job has run.

Figure extraction is heuristic and needs visual inspection. OCR is not bundled; scanned PDFs are flagged. TeX flattening is not a complete TeX interpreter. Missing weights/code prevent reproduction claims. This release does not claim comprehensive live-network or real-publication-layout validation.

See `SKILL.md`, `references/`, `scripts/`, and `tests/`. MIT, upstream copyright © 2026 skJack; see [LICENSE](LICENSE).
