# Changelog

## 0.2.0 — 2026-10-29

Enhanced derivative of upstream snapshot `925953b15813f18b25eeb1a1dca9790f54a47498`.

### Reading workflow
- Quick assessment, guided reading, and project application modes.
- Required assessment of central experiments and limitations; evidence provenance and uncertainty.
- Domain checklists for robotics, speech, video, medical AI and non-model papers.
- Environment-aware formulas/figures, reading progress, and private user-preference handling.
- Corrected a sample's unsupported inference from near-zero action means.

### Reliability
- Confine archive members and TeX includes to the source directory; bound downloads and archive expansion.
- Pin arXiv versions; record PDF/source hashes and selected code commits; preserve cached metadata on API failure.
- Distinguish code candidates from manually selected repositories; validate existing repository origins.
- Preserve manual figure corrections and user-owned directories; validate crop parameters and PDF provenance.
- Add quick/offline material preparation, atomic manifest writes, and offline regression tests.

### Migration
- Automatic discovery no longer clones a repository or labels it official. Supply `--code` after checking it.
- Use a new directory for a different PDF/version. Resume by passing the existing directory.
- Legacy source provenance is unverified until checked against the PDF. Legacy figures without hashes are protected.
- Python 3.10+ is required. No automatic installation into the host agent is performed.

### Validation scope
Offline synthetic regression tests and a synthetic-paper reading exercise. Real-world layout accuracy, live downloads, hardware deployment and clinical effectiveness are not validated by these tests.
