---
description: Edit existing astro-static site
agent: astro-static/orchestrator
---

<summary>
You MUST reopen and update an existing astro-static project.
You SHOULD identify the minimal pipeline phases that need to rerun.
You MUST validate and redeploy the project after applying the requested changes.
</summary>

<user_guidelines>
$ARGUMENTS
</user_guidelines>

<objective>
You MUST take the user's requested changes, bind them to the correct astro-static project workspace, update the right pipeline artifacts, rerun only the necessary orchestration phases, and report the deployed result.
</objective>

1. Determine the project root:
   - Prefer the current directory if it already contains `pipeline/00-brief.json` or `pipeline/vps-connection.json`.
   - Otherwise ask which project to edit and use `/Users/djesys/SITES/<project_name>`.
   - The local pipeline directory is always `/Users/djesys/SITES/<project_name>/pipeline`.
2. Read the current pipeline state and artifacts before making changes:
   - `pipeline/00-brief.json`
   - `pipeline/01-creative-brief.json` if present
   - `pipeline/02-asset-manifest.json` if present
   - `pipeline/00-pipeline-state.json` if present
3. Interpret the change request and choose the smallest sufficient rerun scope:
   - Research / IA / page-structure changes → update the brief and rerun from Phase 2 or 2.5
   - Branding / colors / fonts / image direction → rerun from Phase 3
   - Layout / component / frontend implementation changes → rerun from Phase 4
   - Mixed requests → rerun from the earliest affected phase
4. Update `pipeline/00-brief.json` and any other required pipeline artifact so the current orchestrator has an accurate source of truth.
5. Validate changed artifacts before rerunning phases.
6. Resume the orchestrator from the earliest affected incomplete phase. Do not wipe completed work unless the user explicitly asks for a clean restart.
7. Run the relevant validations and deploy path for the current profile.
8. Finish with a concise summary of what changed, which phases reran, where the project lives locally, and the resulting live URL or blocker.
