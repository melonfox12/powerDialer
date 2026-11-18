# Known issues and oddities

Recorded during handbook and annotation work. **Do not fix here** — comments-only annotation policy.

| Location | Line (approx) | Issue |
|----------|----------------|-------|
| `web.py` | 93–94 | Special-case route param parsing for `/api/leads/{id}` only; other `{id}` patterns use generic splitter in `_match_pattern` |
| `features/dialer.py` | (varies) | `Dialer` class is large; session logic split across `features/_dialer/*` but facade remains in one file |
| `docs/ARCHITECTURE.md` vs app | — | `docs/` describes an older target tree in places; `.cursor/rules/project-map.mdc` is closer to current layout |
| Metrics vs performance | — | Two analytics paths: bump store (`/api/metrics`) vs CRM-derived (`/api/performance`); see `docs/ARCHITECTURE.md` |
| `PUBLIC_API_PATHS` | `shared/config.py` | AI voice bridge endpoints bypass normal Google auth when secret matches (by design) |

_Add rows as annotation batches discover more._