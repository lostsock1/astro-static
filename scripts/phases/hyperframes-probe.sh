#!/usr/bin/env bash
# hyperframes-probe.sh — Probe control node for HyperFrames toolchain availability.
# Called by: orchestrator (Phase 3.8 probe) and hyperframes-vid-gen subagent (preflight).
# Emits:  STATUS:HYPERFRAMES_AVAILABLE | STATUS:HYPERFRAMES_UNAVAILABLE reason=<...>
# Exit:   0 on available, 0 on unavailable (missing toolchain is not a pipeline error),
#         1 on probe script error (should not happen).
set -euo pipefail

NODE_VERSION=$(node --version 2>/dev/null | grep -oE '[0-9]+' | head -1 || echo "0")
FFMPEG=$(ffmpeg -version 2>/dev/null | head -1 || echo "MISSING")
HF_SKILLS=$(ls ~/.agents/skills/hyperframes/SKILL.md 2>/dev/null | wc -l | tr -d ' ')
HF_CLI_SKILLS=$(ls ~/.agents/skills/hyperframes-cli/SKILL.md 2>/dev/null | wc -l | tr -d ' ')
HF_ANIM_SKILLS=$(ls ~/.agents/skills/hyperframes-animation/SKILL.md 2>/dev/null | wc -l | tr -d ' ')

if [ "${NODE_VERSION}" -lt 22 ]; then
  echo "STATUS:HYPERFRAMES_UNAVAILABLE reason=node_too_old version=${NODE_VERSION} need=22"
  exit 0
fi

if [ "$FFMPEG" = "MISSING" ]; then
  echo "STATUS:HYPERFRAMES_UNAVAILABLE reason=ffmpeg_missing"
  exit 0
fi

if [ "${HF_SKILLS}" -eq 0 ]; then
  echo "STATUS:HYPERFRAMES_UNAVAILABLE reason=skills_not_installed install_hint='npx skills add heygen-com/hyperframes --yes'"
  exit 0
fi

echo "STATUS:HYPERFRAMES_AVAILABLE node=${NODE_VERSION} ffmpeg=present skills=${HF_SKILLS} cli=${HF_CLI_SKILLS} anim=${HF_ANIM_SKILLS}"
exit 0
