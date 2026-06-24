---
description: Attach domain to astro-static site
agent: astro-static/orchestrator
---

<summary>
You MUST attach or switch a domain for an astro-static project safely.
You SHOULD reuse the existing project metadata and bootstrap tooling instead of hand-editing random infrastructure.
You MUST validate DNS, project config, and the resulting live URL before finishing.
</summary>

<user_guidelines>
$ARGUMENTS
</user_guidelines>

<objective>
You MUST bind a new domain to an existing astro-static project by updating the local project metadata, applying the appropriate VPS-side configuration safely, validating the result, and reporting the final site and repo URLs.
</objective>

1. Determine the project root from the current directory or ask the user to choose an existing project under `$HOME/SITES/`.
   - The local pipeline directory is always `$HOME/SITES/<project_name>/pipeline`.
2. Read `pipeline/vps-connection.json` first and preserve its existing SSH and project settings.
3. Ask for any missing domain inputs one group at a time:
   - base domain
   - optional explicit project host override
   - whether the domain is a first attachment or a replacement of an existing domain
4. Confirm the required DNS records are in place before making remote changes.
5. Prefer the current astro-static bootstrap workflow as the source of truth:
    - reuse `~/.config/opencode/astro-static/setup-vps.sh` and the project's existing connection details when that is the safest path
    - use `FORCE_PROJECT=true` for domain replacement so the per-project Caddy fragment is regenerated instead of silently preserved
    - if the Gitea public URL changes, update `/etc/gitea/app.ini` `ROOT_URL` intentionally and restart Gitea; do not assume setup idempotency will rewrite it
    - avoid ad-hoc infrastructure edits when an explicit idempotent project-phase rerun can express the change
6. Update local metadata so `pipeline/vps-connection.json` reflects the intended domain-mode values and resulting site URL.
7. Validate the updated config, then run the necessary remote/project configuration to make the domain live.
8. Verify:
   - the project URL answers successfully
   - the repo URL still works if Gitea is involved
   - local pipeline metadata matches the live result
9. Finish with the final site URL, any changed repo URL, and any follow-up DNS or propagation caveat.
