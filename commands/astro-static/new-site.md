---
description: Start astro-static site pipeline
agent: astro-static/orchestrator
---

<summary>
You MUST start or resume a full astro-static site pipeline.
You SHOULD gather missing VPS and brief details one group at a time.
You MUST leave the project with valid startup artifacts and run the current orchestrator flow.
</summary>

<user_guidelines>
$ARGUMENTS
</user_guidelines>

<objective>
You MUST turn the user's seed request into a valid astro-static project workspace, create or update the required pipeline artifacts, validate them, and then run or resume the current astro-static orchestrator.
</objective>

1. Treat the user's text as seed input only. Ask for missing details one group at a time.
2. Determine the project root:
   - If the current directory already contains `pipeline/00-brief.json`, `pipeline/vps-connection.json`, or `pipeline/00-pipeline-state.json`, use it.
   - Otherwise derive or confirm `project_name` and work in `/Users/djesys/SITES/<project_name>`.
   - The local pipeline directory is always `/Users/djesys/SITES/<project_name>/pipeline`.
3. Collect the minimum startup data before launching the pipeline:
   - VPS connection: `ssh_host`, `ssh_port`, `ssh_user`, `ssh_key`
   - Project identity: `project_name`, `client_name`, `site_type`
   - Brief seed: location, goals, required pages, reference URLs, competitor URLs, existing brand status
4. Create or update `pipeline/00-brief.json` with at least:
   - `schema_version`
   - `project_name`
   - `client_name`
   - `site_type`
   Add any other known brief fields rather than dropping them.
5. Create or update `pipeline/vps-connection.json` with at least:
   - `schema_version`
   - `project_name`
   - `ssh_host`
   - `ssh_port`
   - `ssh_user`
   - `ssh_key`
   If the user already knows the target domain, include it. Otherwise preserve an existing value or omit optional fields rather than inventing them.
6. Validate before proceeding:
   - `jq -e '.schema_version and .project_name and .client_name and .site_type' pipeline/00-brief.json`
   - `jq -e '.schema_version and .project_name and .ssh_host and .ssh_port and .ssh_user and .ssh_key' pipeline/vps-connection.json`
   - `python3 ~/.config/opencode/astro-static/validate-pipeline.py --phase startup . --pipeline-dir pipeline/` once both files exist
7. If a pipeline state file already exists, resume rather than restarting unless the user explicitly asks for a reset.
8. Run the current astro-static orchestrator flow through completion or until it halts for human review.
9. Finish with the active phase, live URL if available, project root, and any blocker that still needs human action.
