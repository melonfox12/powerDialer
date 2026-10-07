# Agent rules

- Group code by what it does and what changes together, not by file size. Split a file only when it has two separate reasons to change or mixes pure logic with side effects. Size is checked last; up to ~500 lines is fine for a cohesive file.
- A boundary must pass this test: can someone understand and change file A without opening file B? If not, they are one unit.
- No folders for 1-2 files. No re-export-only files or barrel `__init__.py`/`index.js` files that import siblings.
- No mixins, multiple inheritance, `__getattribute__`, method registries, or `getattr`/`hasattr` duck-typing between our own modules. Dependencies are explicit imports or constructor arguments.
- Pure logic (rules) is separate from I/O (storage, Twilio, HTTP). Business rules live in exactly one place.
- Constants (statuses, timezones, API paths, required keys) are defined once and imported.
- Dependency direction: web -> dialer -> leads, settings -> storage -> shared. Lower layers never import higher ones.
- Before deleting anything, search the repo (`.py`, `.js`, `.html`, tests, string references) to confirm zero references.
- Never touch `.env` or `crm_data/`.
