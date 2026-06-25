---
description: Guided wizard to start (or resume) an astro-static site pipeline
agent: astro-static/orchestrator
---

<summary>
You MUST run an interactive, staged setup wizard, then start or resume the full astro-static pipeline.
You MUST ask one stage at a time, pre-fill smart defaults from the seed, and confirm before launching.
You MUST explicitly ask whether to scrape an Instagram account and how to use it.
You MUST leave the project with valid startup artifacts, then run the current orchestrator flow to completion or a human-review halt, and finish with the operator completion summary (live URL, credentials, and the generation report).
</summary>

<user_seed>
$ARGUMENTS
</user_seed>

<wizard>
Treat the seed as input only — never invent business facts. Conduct a friendly, numbered interview. For each stage: pre-fill whatever the seed already implies, show it, and ask only for what is missing or needs confirmation. Accept answers by number or free text. Ask one stage at a time — do not dump every question at once.

**Resume shortcut:** if the working directory or `$HOME/SITES/<project_name>` already contains `pipeline/00-pipeline-state.json`, skip the wizard and resume the pipeline from the first incomplete phase (unless the user explicitly asks to reset).

### Stage 1 · Project
- `project_name` — a slug matching `^[a-z0-9][a-z0-9-]{0,62}$`; propose one derived from the client/seed and confirm.
- `client_name` — the real business/person name.
- `site_type` — e.g. restaurant, bar, portfolio, SaaS landing, agency; optional `site_category`.
- `location` — city/region, if relevant.

### Stage 2 · Server (VPS)
- `ssh_host` (IP or hostname) · `ssh_user` (default `debian`) · `ssh_port` (default `22`).
- `ssh_key` — path to the private key; default `$HOME/.ssh/id_ed25519`. Confirm the file exists.
- `domain` — ask:
  1. **auto** — a free, instant `<project>.<ip>.sslip.io` URL with automatic HTTPS *(recommended)*
  2. a real domain you already point at the VPS
  3. none
  Default **1 (auto)**.
- Before leaving this stage, run the connection preflight (key file exists + `ssh … "echo STATUS:CONNECT_OK"` with `BatchMode=yes`, `StrictHostKeyChecking=accept-new`, `ConnectTimeout=10`). If the host key changed (reprovisioned VPS), tell the operator and offer to clear the stale `known_hosts` entry. If unreachable, surface it and let the operator fix the host/key before continuing.

### Stage 3 · Brand & references
- Existing brand assets? `has_logo` / `has_colors` / `has_photography` (+ `assets_paths` if yes) → `existing_brand`.
- `reference_urls` — sites whose look & feel to draw from (optional, multiple).
- `competitor_urls` — optional.

### Stage 4 · Instagram (always ask)
- "Do you have an Instagram account to pull from? Enter the handle (with or without `@`), or say *skip*."
- If provided, strip a leading `@` → `instagram_handle`, then ask how to use it (map the answer to `instagram_use`):
  1. **Design reference only** → `design_reference` (tokens/visual style, Phase 1)
  2. **Brand research only** → `brand_research` (voice/positioning, Phase 2)
  3. **Content / photos source** → `content` (real photos become content images, and image-to-video backgrounds)
  4. **Everything — design + brand + content** → `both` *(recommended for image-rich brands)*
- Tell the operator: scraping runs through the Camoufox-backed `search/instagram` agent; with `content`/`both`, real posts are selected as content images before any AI generation, and animated into video backgrounds via image-to-video.

### Stage 5 · Content
- `goals` — what the site should achieve.
- `required_pages` — or let research propose them from the brief.

### Stage 6 · Confirm & launch
Echo a compact summary of every collected value and ask **"Proceed? (yes / edit <stage>)"**. On *yes*, write the artifacts, validate, and launch.
</wizard>

<finalize>
1. **Project root:** the cwd if it already holds pipeline artifacts, otherwise `$HOME/SITES/<project_name>`. The pipeline directory is always `<root>/pipeline`.
2. **Write `pipeline/00-brief.json`** with at least `schema_version`, `project_name`, `client_name`, `site_type` — plus every other collected field (`site_category`, `location`, `goals`, `reference_urls`, `competitor_urls`, `domain`, `required_pages`, `existing_brand`, `instagram_handle`, `instagram_use`). Never drop a value the operator gave you.
3. **Write `pipeline/vps-connection.json`** (mode `0600`) with `schema_version`, `project_name`, `ssh_host`, `ssh_port`, `ssh_user`, `ssh_key` (+ `domain` if known).
4. **Validate before launching:**
   ```bash
   jq -e '.schema_version and .project_name and .client_name and .site_type' pipeline/00-brief.json
   jq -e '.schema_version and .project_name and .ssh_host and .ssh_port and .ssh_user and .ssh_key' pipeline/vps-connection.json
   python3 ~/.config/opencode/astro-static/validate-pipeline.py --phase startup . --pipeline-dir pipeline/
   ```
5. **Run the orchestrator flow** to completion or a human-review halt. If a state file already exists, resume rather than restart unless asked to reset.
6. **Finish with the completion summary** (orchestrator Phase 5): the live Site URL, the credentials handoff, and the full generation report of problems, bugs, gaps, and inefficiencies encountered during the build.
</finalize>
