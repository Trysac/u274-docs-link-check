# Project record

## Objective

Check links in Markdown documentation: relative files with exact case, heading anchors with GitHub slugs, root escapes, and external URLs through an injected HTTP checker with caching

## Scope

- In scope: the public API documented in [README.md](../README.md), typed and tested.
- Out of scope: anything that needs runtime dependencies, or network access outside the injected
  `HttpChecker` port.

## Timeline

| Date | Event |
|---|---|
| 2026 | Repository created from the factory utility template. |

## Effort metrics

Measured values only; a value that has not been measured stays "pending measurement".

| Metric | Value |
|---|---|
| Tokens (input / output) | 2370670 / 117994 |
| Hours (human) | pending measurement |
| Cost (USD) | 0.1482 |

## Factory run u274 (measured from API usage)

| Date (UTC) | Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|---|
| 2026-11-11 | generation | deepseek-v4-pro | yes | 1795 | 29084 | 0 | 3328 | 0.0588 |
| 2026-11-11 | fix-1 | deepseek-flash | no | 26890 | 16612 | 0 | 480640 | 0.0154 |
| 2026-11-11 | fix-2 | deepseek-flash | no | 20354 | 15616 | 0 | 268416 | 0.0132 |
| 2026-11-11 | fix-3 | deepseek-flash | no | 12328 | 512 | 0 | 32128 | 0.0023 |
| 2026-11-11 | audit | deepseek-flash | no | 35649 | 29466 | 0 | 623488 | 0.0249 |
| 2026-11-11 | fix-4 | deepseek-flash | no | 23218 | 10704 | 0 | 763904 | 0.0122 |
| 2026-11-11 | docs | deepseek-flash | no | 78276 | 16000 | 0 | 256 | 0.0213 |

Total: $0.1482. Prices: deepseek line, as measured by its adapter. Providers serve the current version of each model id, so the date tells which version answered; versions, launch stages and price sources per line are in the factory's model register (docs/MODELS.md).
