# Pipeline hardening — 2026-11-07

Scope: improve the shared generator based on the mount-devil run. The existing client site, credentials and VPS are not modified. No commits, pushes, reboots or real-site content writes are part of this maintenance run.

## Source and installation

- Source of truth: this repository, not the old installed `agents/astro-static/scripts/` snapshot.
- Active scripts: `~/.config/opencode/astro-static/`.
- Agent prompts/references/schemas: `~/.config/opencode/agents/astro-static/`.
- Changes are installed selectively; a full destructive sync is intentionally not used because unrelated source/install drift existed before this work.

## Scaffold verification completed

- Explicit `admin-blocks` default has no preview routers or placeholder island endpoint. Explicit legacy overlay retains its POST endpoint.
- Public origin and an exact Astro proxy-host allowlist are generated from the resolved site URL. Cookie security uses the trusted origin. The SSR listener remains loopback-only.
- Signed sessions reject malformed, duplicate, future and expired tokens. Browser-origin protection, bounded bodies and per-client login throttling are tested.
- The durable login source lives in `public/admin/login.html`; both the canonical local-build phase and generated package build restore it after Tina replaces `admin/`.
- Direct dependencies are pinned to the verified compatible baseline. The Tina integration's Astro 5/6 peer declaration remains an explicit caveat with the required Astro 7 stack; it is not hidden by forced peer installation.

Evidence collected on a disposable local scaffold, not on the live client:

1. `bun install`: 1301 packages installed; one disclosed Astro/Tina peer warning and one withheld optional postinstall.
2. Default-mode Astro check: zero errors, warnings or hints. Explicit overlay check: zero errors, warnings or hints.
3. Real local Tina admin build and Astro server build completed. A cold Tina bundle took approximately seven minutes; the Astro build took approximately 1.5 seconds.
4. Twelve scaffold regressions pass with installed dependencies. The tests execute the real pinned Tina backend with only database execution isolated, and real Astro forwarded-address handling.
5. A built local SSR server with the real Tina database answered login/session/read-only GraphQL successfully. One client's exhausted login budget did not block another client; hostile Origin was rejected. Only fixture credentials were used and no content mutation was performed.
6. Independent scoped review found no remaining substantive scaffold findings after corrections.

## Shared hardening completed

- Mode-aware generator prompts, examples, schemas and validator agree: admin-blocks has no preview routers or overlay requirements; legacy overlay retains them. The durable login and installed dependency intersections are validated.
- Explicit Instagram skip is schema-valid. Advisory research findings remain tracked follow-ups; factual/rights/essential-content blockers still halt. Explicitly declined video generation no longer emits a missing optional-shot-list warning.
- The wizard discloses staging verification requirements before launch. New CMS-complete briefs require source/deployment-bound staging and real-browser evidence at the final gate; legacy completed sites are not retroactively authorized for writes.
- A distinct staging build origin is selected only with explicit staging environment flags, leaving source files identical to the target deployment. Canonical JSON source identity allows lossless formatting changes on restoration; raw hashes remain audit evidence, not a false byte-equality requirement.
- Credential handoff instructions provide clearly labeled private retrieval/copy commands, never passwords or field names presented as passwords.
- Bootstrap no longer removes known SSH keys automatically, and automation is noninteractive. A changed key requires operator verification.
- Git publication resets inherited credential helpers only for the invocation, preserves existing Git operation state, fails on genuine staging errors and excludes private artifacts, including previously tracked backup/recovery files, from the new snapshot. Existing Git history is not rewritten.
- Push supervision has bounded local process-tree cancellation and a remote deadline capped by the overall and fallback budgets, including connection time. Nested cancellation preserves escalation grace. Default caller allowance is 620 seconds for the 600-second inner budget; control/VPS clocks must be synchronized for the shared epoch bound. A timeout never proves the remote ref was unchanged: inspect it before retrying.
- Portable retry signatures have a line-based helper, avoiding caller-computed hash mismatches.
- The staging-only save/persist/live/restore gate requires explicit operator attestation and source identity, protects startup artifacts from report-path overwrites, supports exactly one standard settings document (`global.json` or `site.json`), retains private recovery on indeterminate writes, checks decoded visible brand text, and enforces request/poll wall-clock deadlines. It cannot cancel a server-side mutation after transport loss; that outcome is MANUAL_REVIEW even if current rollback readbacks look clean.

## Final combined verification

Both the canonical source and selectively installed runtime passed **202 tests**, with no failures or skips:

| Module | Tests |
|---|---:|
| Baseline regressions | 115 |
| Mode/schema/dependency/evidence contracts | 14 |
| Bootstrap/publication/timeout/retry operations | 25 |
| Generated scaffold/auth/proxy behavior | 12 |
| Staging gate orchestration and recovery | 36 |

Commands (set `SCAFFOLD_NODE_MODULES` to the disposable scaffold's installed dependencies):

```sh
python3 -m unittest discover -p 'test_*.py'
```

Source suite: 202 tests, 131.790 seconds, OK. Runtime suite: 202 tests, 131.784 seconds, OK. Regression cases include the independently reviewed escaped-restoration marker, delayed save committing after rollback, slow-drip response deadlines, intermediate-shell cancellation and delayed remote execution.

Additional checks:
- Final generated scaffold check: 21 files, zero errors/warnings/hints. Explicit staging-environment Astro build passed, preserving source identity.
- Shell syntax, Python compilation and `git diff --check` passed.
- All 25 changed installable files match their installed counterparts byte-for-byte. Private backups and the install manifest are under `~/.config/opencode/astro-static/backups/`.
- OpenCode definitions resolve through this installed version's `opencode debug agents`; the older `opencode agent list` command is not supported here.
- The existing mount-devil site's local final validator remains compatible: `VALIDATION_OK [final]`, no missing optional-video warning. No site files or VPS state were changed.

Verification logs are in the approved local OpenCode temporary directory (`hardening-source-final.log`, `hardening-runtime-final.log`). Repository publication is a separate operator-authorized step; consult Git history and the pull request for publication status.

## Verification boundary

The staging roundtrip test harness simulates Tina/watcher behavior. No authorized real staging deployment was supplied, so an actual save → persistence → rebuild → published change → restoration remains **UNVERIFIED**. Adding the gate does not retroactively verify the already-live client's persistence path. The disclosed Astro 7/Tina integration peer caveat also remains; do not force upgrades or hide it. The client's pending security/kernel reboot remains an operator task, not an action performed by this maintenance run.
