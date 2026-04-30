# Known Limitations (v0.1.0-mvp)
Date: 2026-04-21

## Scientific and algorithmic
1. Some algorithm branches are still engineering implementations and not full production scientific references.
2. Non-GPS `SIGMA_PHI_F` remains experimental and should not be treated as equal to GPS formal pipeline outputs.
3. `DIXSG` grid confidence and coverage depend on available stations and geometry quality.

## Data and dependencies
1. PPP/orbit/clock/antenna providers are currently stub/basic strategy in MVP.
2. NAV fallback is treated as degraded mode and should be explicitly interpreted as lower confidence.
3. Input filename/date inference supports major patterns but can still require normalization for uncommon naming.

## UI and workflow
1. Report center export is lightweight text-based MVP output, not final production PDF template system.
2. Some advanced UI_SPEC_V3_1 visual overlays (full mask layers and annotation richness) are partially implemented.
3. Template governance and multi-role workflows are MVP scope only.

## Performance and scale
1. Long-batch throughput and heavy-grid memory optimization are not fully tuned.
2. Very large multi-day/multi-station runs may require manual batching in current MVP.

## Compatibility
1. Current priority platform is Windows.
2. Linux/macOS support is not fully validated in this release.

## Release and operations
1. Current Windows release route is portable package (local venv), not MSI installer.
2. New machine installation requires Python 3.11 launcher (`py -3.11`) available.
3. Multi-machine rollout currently relies on scripted package generation, not centralized auto-update service.
