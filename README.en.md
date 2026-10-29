# kelip-paper-reading · v0.2.0

[简体中文](README.md) · [Release notes](CHANGELOG.md)

Read and critically assess a paper through its original figures, equations, examples and implementation. Choose **quick assessment**, **guided reading**, or **project application**. Every mode addresses the central experimental evidence and its limitations. Respect requests to skip sections or receive one complete answer.

Enhanced derivative of [skJack/kelip-paper-reading](https://github.com/skJack/kelip-paper-reading), based on uploaded snapshot `925953b15813f18b25eeb1a1dca9790f54a47498`. The upstream MIT notice is preserved. This is not an upstream release or endorsement.

## What changed in this version?

The upstream snapshot already provides six-stage guided reading, original-figure explanations, numeric examples, paper/code comparison, and notes. This derivative retains that foundation and strengthens **evidence assessment, intent-based reading, project evaluation, and material integrity**. Comparisons below refer to the imported snapshot, not later upstream releases.

### Reading and analysis

| Area | Upstream default | v0.2.0 change | Benefit |
|---|---|---|---|
| Reading mode | Stage-by-stage teaching with continuation prompts | Quick assessment, guided reading, and project application; respect one-answer requests | Match the depth and pacing to the user's goal |
| Experiments | Results and standing are an optional seventh stage | Central results and at least one evidence limitation in every mode | Evaluate whether the evidence supports the method's claims |
| Fair comparison | Describe results, baselines and limitations | Check data, pretraining, model size, training/inference budgets, ablations, repeated runs and external tests | Avoid attributing a resource advantage to an architectural idea |
| Traceability | Distinguish paper, code and inference; cite numbers | Evidence table with source/version, PDF location, code commit, conditions and support level | Make claims easier to audit; separate reported and independently measured results |
| Examples | Real numbers and toy examples | Trace real samples; label illustrative values and omitted assumptions; correct the unsupported near-zero-mean/action-delta inference | Keep explanations accessible without treating examples as proof |
| Domains | Primarily robotics, VLA and world-model examples | Speech, video, medical/pathology AI, theory and review checklists | Inspect the relevant metrics and validation requirements |
| Project application | Resource and deployment questions within teaching | Explicit gap table and minimum validation plan, including acceptance and stop criteria | Decide what is worth testing before committing to integration |
| Display and progress | Unicode formulas, text diagrams, reading notes | Host-aware rendering, material-linked progress template, private preference storage | Improve readability, resumption and shared use |

These are agent instructions and templates. Actual explanation quality depends on the executing model, available evidence and verification. This release improves the reading workflow and source handling; it does not establish performance gains for the models described in papers.

### Reliability fixes

| Issue or scenario | v0.2.0 behavior | Implementation |
|---|---|---|
| Archive sibling-prefix traversal or TeX inclusion outside source | Resolve and check path containment; reject special entries; bound downloads and expansion | `common.py`, `fetch_paper.py` |
| New metadata combined with an old PDF/source | Pin versions and record hashes; stop on identity mismatch; use another directory for another version | `fetch_paper.py` |
| API failure losing cached author/abstract fields | Preserve valid cached metadata | `fetch_paper.py` |
| A high link score treated as official ownership | Discovery yields candidates; `--code` records a checked manual selection | `fetch_paper.py` |
| Any nonempty folder accepted as cloned code | Validate Git origin and commit; record offline missing code as `not-cloned` | `fetch_paper.py` |
| Reruns overwriting manual crops | Protect corrections by flags/hashes and preserve user-owned directories | `extract_figures.py`, `crop.py` |
| Direct extraction bypassing PDF provenance | Check the recorded PDF hash in standalone extraction and `paper.pdf` cropping | `extract_figures.py`, `crop.py` |
| Derived-output symlinks overwriting unrelated files | Atomic replacement for generated outputs; reject crop output symlinks and source overwrite | Shared I/O and processing scripts |
| An invalid PDF poisoning the destination | Validate incoming PDF bytes before installation | `fetch_paper.py` |
| Preparing all materials before a small question | Quick and offline preparation options | `fetch_paper.py` |
| Invalid crop parameters or missing output directories | Check page, box, DPI and grid step; create output parents | `crop.py` |

Scripts track identities and protect files. They do not independently certify official ownership, scientific validity, or deployment suitability.

### Example and validation scope

For “Can this video model replace my current system?”, application mode explains the task and results, checks comparison conditions and generalization, separates supported claims from unknowns, and proposes a small evaluation with metrics and stop criteria. A GPU benchmark is not treated as CPU latency; missing external validation remains an unresolved deployment question.

- **37 offline regression tests** cover material identity, cached metadata, paths, files, figures, offline operation and recovery.
- **Python 3.10, 3.12 and 3.13 all passed** for v0.2.0 in [GitHub Actions](https://github.com/blueapple2000/kelip-paper-reading/actions/runs/40873936654).
- Independent checks exercised edge cases, and one synthetic-paper reading exercise assessed the workflow.
- Long-term live-download reliability, diverse real-publication layouts, broad explanation-quality benchmarks and real deployment performance remain unverified.

See [CHANGELOG.md](CHANGELOG.md) for the release change list.

## Setup

Python **3.10+**, PyMuPDF, and optional Git. This repository is public and can be browsed, downloaded or cloned directly.

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

Offline tests use synthetic PDFs, archives, repositories and mocked network responses. For v0.2.0, all 37 tests passed on Python 3.10, 3.12 and 3.13 in GitHub Actions. Local validation used Python 3.12 / PyMuPDF 1.26.6. The linked run records that release; check Actions for later commits.

Figure extraction is heuristic and needs visual inspection. OCR is not bundled; scanned PDFs are flagged. TeX flattening is not a complete TeX interpreter. Missing weights/code prevent reproduction claims. This release does not claim comprehensive live-network or real-publication-layout validation.

See `SKILL.md`, `references/`, `scripts/`, and `tests/`. MIT, upstream copyright © 2026 skJack; see [LICENSE](LICENSE).
