# Claude Code automation recommendations — HTX

Codebase profile: pure-Python analysis repo (stdlib + `openpyxl` + `python-pptx`, 1,071 LOC in
`analysis/`), no git, no tests, no JS. Deliverables are a Markdown report and a .pptx deck built
from large read-only source data (`WBM*/`, 3,698 FASTQs).

---

## 1. Hook — protect the read-only inputs (highest value)

The instruction "never write `HTX_biosurveillance_briefing_modifed.pptx`" currently lives only in
prompt context and dies at every compaction. Same for the raw sample folders and `sampleInfo.xlsx`
(source of truth, no backup, not in git). Make it structural.

`.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Edit|Write|NotebookEdit",
      "hooks": [{
        "type": "command",
        "command": "python3 -c \"import json,sys,re; p=json.load(sys.stdin)['tool_input'].get('file_path',''); sys.exit(2) if re.search(r'_modifed\\\\.pptx$|^/data/alvin/HTX/WBM\\\\d+/|sampleInfo\\\\.xlsx$|MGI PPT templates', p) else None\""
      }]
    }]
  }
}
```

Exit code 2 blocks the call and returns the reason to Claude. Extend the regex rather than adding
hooks.

## 2. Hook — syntax-check edited analysis scripts

Every `analysis/*.py` is run manually and a syntax error costs a full round trip.

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{
        "type": "command",
        "command": "f=$(python3 -c \"import json,sys;print(json.load(sys.stdin)['tool_input'].get('file_path',''))\"); case \"$f\" in *.py) python3 -m py_compile \"$f\";; esac"
      }]
    }]
  }
}
```

## 3. Skill — `render-deck` (user-invocable)

`.claude/skills/render-deck/SKILL.md`. Wraps the manual QA loop repeated ~8 times this session:

```yaml
---
name: render-deck
description: Render HTX_biosurveillance_briefing.pptx to PNGs and check every slide for overflow
disable-model-invocation: true
---
```

Body: `soffice --headless --convert-to pdf --outdir /data/alvin/tmp/deckpng <pptx>` then
`pdftoppm -png -r 70`, then read the PNGs and report any text crossing the 7.5" slide boundary or
overlapping the footer. Bundle the paths so they are not re-derived each time.

## 4. Skill — `deck-style` (Claude-only)

`.claude/skills/deck-style/SKILL.md` with `user-invocable: false`. Encodes the geometry and font
contract that currently has to be re-read from `HTX_biosurveillance_briefing_modifed.pptx`:
Arial, `MIN_PT = 12.0` floor, title 26 pt at (0.5, 0.28) w=12.4, subtitle 12 pt at (0.5, 0.88),
blue rule at (0.5, 1.22) 12.33×0.028, per-sample species table at (0.5, 2.15) w=5.9, flaggable
items at x=6.95 spaced 0.72. Plus the rule: `_modifed.pptx` is the reference, never the target.

## 5. Subagent — `deck-qa`

`.claude/agents/deck-qa.md`, tools `Read, Bash`. Renders and visually reads all 19 slide PNGs and
returns only a list of overflowing slides. Keeps ~19 images out of the main context — the specific
thing that consumed context repeatedly during the deck build.

---

## Skipped, and why

- **MCP servers** — no database, no frontend, no GitHub remote, no external API. `context7` would
  only serve `python-pptx`/`openpyxl` doc lookup; marginal against local `help()`.
- **Plugins** — nothing here needs a bundle beyond the two skills above.
- **Test hooks / tdd** — the analysis scripts are one-shot derivations validated against the raw
  data, not a library with a suite worth wiring to a hook.

## Not an automation, but the biggest single fix

`git init`. The repo is untracked: `docs/biothreat_assessment.md` went v1→v3, `build_deck.py` was
rewritten repeatedly, and the only protection for `_modifed.pptx` is remembering not to touch it.
Add `WBM*/`, `assembly/*.fa`, `*.fq.gz` to `.gitignore` and commit the scripts, docs and TSVs.
