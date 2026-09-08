# abs-risk — working agreement for Claude Code sessions

Consumer credit risk from public SEC filings. Two tracks: card master trust pools (10-D + prospectus
composition tables) and loan-level auto ABS (Form ABS-EE exhibit 102). One person, Claude writes most code.
Separate from the credit-card-data dashboard (C:\Users\samwe\code\credit-dashboard); do not merge them.
Design: PLAN.md. Task board: TASKS.md. Scouting notes: design/scout-*.md.

## Start and end of every session
- Start: read TASKS.md, run `python -m uv run pytest`, report status before doing anything.
- One bounded task per session, with the pass condition written in TASKS.md before work starts.
- End: tests green, `git commit` with a plain message, push to origin, TASKS.md updated, one-paragraph handoff.

## EDGAR rules (non-negotiable)
- Every request goes through `absrisk.http.make_session()`: project User-Agent, 5 requests/second cap, retries.
- Never send a browser User-Agent. Never scrape faster than the cap. Never hit EDGAR from tests (fixtures only).
- Save every downloaded filing under data/raw/<track>/<trust-or-deal>/<accession>/ before parsing it.
- Parse by row label / XML element name, never by position. Fail loudly on anything unexpected.
- Before writing a parser: download the real file, print its structure, then write the parser and a fixture test.

## Commands (Windows: prefix with `python -m`)
    uv sync                 # install (creates .venv)
    uv run pytest           # all tests
    uv run absrisk version

## Storage
- Committed: small derived tables under data/, docs/ for the published page, fixtures under tests/fixtures/.
- Not committed: data/raw/ (re-downloadable from EDGAR), .venv, .duckdb files.

## GitHub
- Remote: https://github.com/SamuelJWebber/abs-risk (real-name account, `gh` active account). Public.
