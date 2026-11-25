# Resume Tailor - Agent Context

## Project Overview

Resume tool that separates **content** (structured YAML) from **layout** (rules-driven LaTeX template). The local web UI proposes section order, evidence selection, and source-linked wording changes for a pasted JD. Each proposal needs user review; typography and spacing remain fixed. The PDF uses Nimbus Roman No9 L through `mathptmx`, a Times-style font supported by pdfLaTeX.

## Quick Start

```bash
cd /Users/aaryan/Desktop/Sculpt
source .venv/bin/activate
export PATH=/Library/TeX/texbin:$PATH
python build.py
```

Output: `output/resume.pdf` | LaTeX: `output/resume.tex`
Verbose: `python build.py -v`
Tailored: `python build.py --profile tailored --content content/tailored/company_role.yaml`
Web UI: `/Users/aaryan/Desktop/Sculpt/run.sh` from any directory, then open `http://127.0.0.1:8000`. The launcher uses `.venv`, sets the LaTeX path, and forwards server options such as `--port 8001`.

## Environment Setup

- **Python 3.13.12** with venv at `.venv/`
- **Dependencies:** `python-docx`, `pyyaml`, `jinja2`
- **PDF inspection:** Poppler's `pdfinfo` and `pdftohtml`
- **LaTeX:** TeX Live 2026 (BasicTeX), at `/Library/TeX/texbin/`
- **LaTeX compiler:** `pdflatex` (configured in `config/rules.yaml`)
- **PATH fix:** Always `export PATH=/Library/TeX/texbin:$PATH` before building (subprocess doesn't inherit interactive shell PATH)

## Directory Structure

```
resume-tailor/ (project root: /Users/aaryan/Desktop/Sculpt)
├── Master_Resume.docx          # Source Word doc — NEVER modify
├── content/
│   ├── master.yaml             # Master content (SOURCE OF TRUTH)
│   └── tailored/              # Separate per-job YAML files, created as needed
├── config/
│   ├── rules.yaml              # Hard rules (code-enforced layout/content limits)
│   ├── profiles/tailored.yaml  # Tailored-only exactly-5-project rule
│   └── style_guide.md          # Soft AI rules read during guided drafting
├── templates/
│   └── resume.tex.j2           # Fixed LaTeX template (DO NOT modify without approval)
├── output/
│   ├── resume.tex              # Generated LaTeX
│   └── resume.pdf              # Final PDF
├── build.py                    # Main build script — read + modify
├── pdf_checks.py               # Rendered PDF line, font, style, and page checks
├── tailor.py                   # SoCLaaS request and existing-content selection
├── review_flow.py              # Source-linked suggestions and approved edits
├── web_server.py               # Local JD form and PDF preview server
├── web/                        # Browser HTML/CSS/JS
└── README.md                   # User documentation
```

## Architecture

```
Master_Resume.docx (read once) → content/master.yaml (source of truth)
                                   ↓
                           master build or separate tailored YAML
                                   ↓
               config/rules.yaml (+ tailored profile override)
               templates/resume.tex.j2 (shared fixed template)
                                   ↓
                  build.py → isolated LaTeX/PDF output
```

### Data Flow

1. **build.py** reads the master YAML by default, or a separate tailored YAML with `--profile tailored --content ...`.
2. Loads `config/rules.yaml`; tailored builds merge `config/profiles/tailored.yaml` over it, setting `content.min_projects: 5`, `content.max_projects: 5`, and the source-aware bullet floor. A tailored YAML may supply an approved `section_order` permutation of experience, education, projects, then skills last.
3. Renders the shared `templates/resume.tex.j2` with placeholder replacement.
4. Compiles LaTeX to PDF using `pdflatex`; tailored output goes under `output/tailored/<content filename>/` unless `--output-dir` is given.
5. Inspects the rendered PDF and LaTeX log for page count, physical line counts, font, styles, section order, project page breaks, and overfull boxes; prints PASS/FAIL and any allowed warning.

### build.py Functions (key entry points)

| Function | Purpose |
|---|---|
| `load_yaml(path)` | Load YAML config files |
| `merge_rules(base, override)` | Apply a small tailored profile without duplicating layout rules |
| `el(text)` | Escape special LaTeX chars (`&`, `%`, `$`, `#`, `_`, `{`, `}`, `~`, `^`) |
| `build_education(entries, rules)` | Generate LaTeX for education section |
| `build_experience(entries, rules)` | Generate LaTeX for experience section |
| `build_projects(entries, rules)` | Generate LaTeX for every project; certifications are rendered inside education |
| `build_skills(skills, rules)` | Generate LaTeX for skills section |
| `generate_section_order(rules, resume)` | Build content in the master default or approved tailored section order |
| `render_latex(rules, resume)` | Full template rendering with placeholder substitution |
| `compile_latex(tex_path, compiler_path)` | Run pdflatex twice |
| `get_pdf_page_count(pdf_path)` | Use `pdfinfo` to count pages |
| `validate(rules, resume, tex_content, output_dir)` | Validate the rendered PDF in its selected output directory; print actionable PASS/FAIL report |

`pdf_checks.py` contains the PDF extraction and layout checks used by `validate`.

## Config Files

### config/rules.yaml

Approved layout values and hard content limits. Keep them aligned with the current PDF. Changes to the frozen LaTeX template still require explicit user approval.

```yaml
layout:
  font: "Nimbus Roman No9 L"
  font_package: "mathptmx"
  font_size: "10pt"
  name_font_size: "14pt"
  line_spread: 0.95
  margins: {top: 0.5in, bottom: 0.5in, left: 0.6in, right: 0.6in}
  page_limit: 2
  max_bullet_lines: 3              # experience, projects, and skills
  max_summary_lines: 4
  max_project_heading_lines: 1
  max_project_title_lines: 1
  project_intro_min_lines: 6
  overfull_tolerance_pt: 3
  section_order: [experience, education, projects, skills]
  compiler: "pdflatex"
  page_size: "letterpaper"
  styles: {...}                    # approved bold, italic, and regular roles
  spacing: {...}                   # exact current margins between elements

content:
  max_bullets_per_entry: 4         # experience and projects; no project count cap
```

`config/profiles/tailored.yaml` requires exactly five projects. Each work/project entry has an effective bullet minimum of `min(3, source bullet count)` and a shared maximum of four: a two-bullet or three-bullet master entry must retain all its bullets. The AI prefers four relevant bullets when available. All master projects remain eligible. The master stays uncapped and has no bullet minimum. Both profiles use the same layout and template.

### content/master.yaml structure

```yaml
contact:
  name, email, phone, github, linkedin, seeking

summary: "paragraph text"

education:
  - institution, degree, dates, modules: [...], tags: [...]
    optional: specialisation, honours, gpa

experience:
  - company, role, tech, dates, bullets: [{id, text, tags}]

certifications:
  - title, org, tags

projects:
  - id, name, competition, placement, tech, dates, bullets: [{id, text, tags}], tags: [...]

skills:
  "Programming Languages": [...]
  "Agentic AI & LLM": [...]
  # Additional ordered display categories, including "Languages"
```

Each project and bullet has a **stable ID** (e.g., `proj1`, `proj1-b1`, `exp1-b3`) for tailored selection and review.

### Templates

**`templates/resume.tex.j2`** — LaTeX template with these placeholders:
- `LAYOUT_*` — font, size, margins, page size, line spread, spacing, and list settings from rules.yaml
- `RESUME_NAME`, `RESUME_EMAIL`, `RESUME_PHONE`, `RESUME_GITHUB`, `RESUME_LINKEDIN`, `RESUME_SEEKING`
- `RESUME_SUMMARY`
- `SECTION_ORDER` — filled by build.py functions

Template uses:
- `mathptmx` (Nimbus Roman No9 L, Times-style)
- `tabular*` for left-aligned bold + right-aligned date layout
- `titlesec` with `[\titlerule]` for section heading underlines
- Compact `itemize` lists and configured `\linespread{0.95}`

## Critical Rules for Agents

1. **NEVER modify `Master_Resume.docx`** — it's the source artifact only
2. **NEVER modify `templates/resume.tex.j2` without explicit approval** — layout is frozen
3. **Always escape LaTeX special characters** — use `el()` function, not raw strings
4. **All spacing/layout is in `rules.yaml`** — don't hardcode vspace or margins
5. **Use `pdfinfo` for page count** (not binary parsing — PDFs are compressed)
6. **LaTeX compiler is at `/Library/TeX/texbin/`** — always resolve full path in subprocess calls
7. **Run `pdflatex` twice** to resolve references/citations
8. **Master content changes only via `master.yaml`**. For a JD, create a separate YAML under `content/tailored/`; retain stable project and bullet IDs.
9. **After any master change, run `python build.py`; after any tailored change, run `python build.py --profile tailored --content ...` and verify all hard checks PASS; review any allowed warnings**
10. **Do not silently drop content or shrink text to meet limits** — report the exact offending entry and text
11. **Tailored resumes select exactly 5 known master project IDs**; the master has no project count cap. Do not overwrite the master PDF during tailoring.

## Git and Deployment Permissions

- Before a task that requires a commit, push, or local Git reset, check the current session's filesystem permissions and `git status`. Do not assume that write access to the project also includes `.git`.
- If local Git writes are permitted, handle staging, committing, pushing, and syncing yourself when the user has authorized that work. Do not hand routine Git commands to the user.
- If `.git` is read-only, report the exact failed operation and permission error. Request elevated access only when the session supports it; a user's approval in chat does not override an enforced sandbox denial.
- When local Git writes are blocked, use an authorized GitHub API or other available publishing path where practical, then explain any remaining local sync step. Never claim that Git is unavailable without checking the specific operation.
- On 2026-10-17, this session allowed project file edits but blocked local Git index writes: `git update-index --refresh` failed while creating `.git/index.lock` with `Operation not permitted`. An elevated `git add` request was automatically rejected because sandbox approval was disabled. The fix was published through the GitHub API, and the user synced the local checkout afterward. Recheck permissions in future sessions; this may change.
- On 2026-10-18, enabling approval requests resolved the blocker: `git add AGENTS.md` succeeded with `sandbox_permissions: "require_escalated"`. Use this supported approval flow for authorized Git operations when available; the sandbox may still protect `.git` during ordinary commands. Do not assume the earlier denial still applies.

## Current State (Checkpoint)

- Baseline PDF builds: 2 pages; all hard checks PASS. One 2.154pt overfull line is reported as an allowed warning under the 3pt threshold.
- All 7 current master projects render and remain eligible for tailoring; tailored resumes require exactly 5 projects and 3–4 bullets per entry when the source has at least 4. A shorter source entry keeps every bullet, including the current two-bullet URECA project. Each bullet may occupy at most 3 physical PDF lines.
- Section structure: Work Experience → Education (including Virtual Training) → Projects → Skills
- Body text is 10pt; name is 14pt. `mathptmx` embeds Nimbus Roman No9 L, not Times New Roman itself.
- Section headings have horizontal underline bars
- Header uses tabular* for left (bold) / right (date) alignment
- Experience and project tech lists are regular weight after `|`
- Each project: header line → "Project: NAME" line → bullets
- Skills: each category on its own line

## Tailoring Workflow

- The default `/` UI now uses guided tailoring: paste JD → confirm company/role/JD → requirements and useful questions → unified review → final PDF. Legacy `/legacy` and its APIs remain for existing `review.json` runs.
- `guided_tailoring.py` analyzes the full JD and full active KB before asking up to four high-value questions. Requirements cite exact JD passages. There is no similarity score. It composes complete role-specific drafts, checks numeric and entry-scoped evidence, renders the PDF, and surfaces evidence findings for review without an automatic rewrite loop. Model audits are fallible; explicit user decisions remain required.
- `staged_generation.py` now uses one holistic writer and one evidence checker (normal path: two main calls). A complete draft is published before checking finishes. Omitted unchanged fields expand from the master; new fields need explicit text. A schema failure gets at most one correction; transport failures stop without content rewrites. No automatic three-pass repair loop.
- Findings distinguish `factual` blockers from non-blocking `suggestion` items. Coverage gaps and editorial preferences must never be factual export blockers. Exact original text and explicit full-passage confirmations need no speculative AI audit. Keep-original removes the flagged proposed claim; manual edits invalidate their exact text/source signature and need a targeted check. Accept alone never clears a factual flag.
- `/api/guided/repair` patches only requested existing field keys. Unrelated proposals and decisions remain unchanged. `/api/guided/check` checks changed passages with full resume context and runs local layout checks. `/api/guided/confirm` requires explicit confirmation of the exact currently displayed passage, stores scoped evidence with `confirmed_passage: true`, and cites it in the decision. New edits invalidate that confirmation. External knowledge changes require rechecking before export.
- Recovery may reuse a valid legacy candidate from the same run's `attempts.json` and recheck it; do not manufacture approvals. New candidates live in `draft.json`, checks/PDFs in `review-checks/`, repairs in `repairs/`. Re-saving identical answers must not invalidate caches. Cache keys include exact inputs, model and prompts.
- Questions must ask one fact/activity at a time. Bare yes/no answers are retained verbatim but treated as uncertain in the evidence catalog, including old compound answers. Never treat sessions OR documentation as proof of either specific activity.

- Role analysis selects numbered `jd_passages` by `passage_id`; the server supplies verbatim quotations from the confirmed JD. Never accept invented passage IDs or loosen quote checks to allow unsupported paraphrases. Older saved analyses with valid quotes remain supported. Schema repair receives the previous response and validation feedback. Before analysis succeeds, the questions screen must clear prior-run questions and hide answer/generation controls.
- SoCLaaS responses use SSE streaming. `SOCLAAS_TIMEOUT_SECONDS` limits connection/read inactivity, not total active generation time. Only completed content is parsed; incomplete streams must fail without applying partial text. Reasoning deltas are discarded and must never enter logs, saved content, or UI progress. Progress callbacks report elapsed time only.
- Substantial rewriting and synthesis within an entry are authorized, including summaries, project descriptive titles, technology lists, skills and bullets. Exactly five known master project IDs, source-aware bullet counts, fixed identities and dates, and all existing layout rules remain enforced. New bullet slots may use confirmed evidence for the same entry; their exported IDs are scoped and stable. Future-project recommendations are never resume evidence.
- `knowledge.py` stores exact questions/answers and manually entered information in ignored `knowledge/knowledge.json`. Kinds: fact, limitation, uncertain, planned; only confirmed facts can support claims. Local readable files are the authorized persistence target. Previous versions are retained in `knowledge/history/`. The app supports edit/archive/export; direct JSON edits are reloaded before analysis/drafting. See `knowledge/README.md`.
- Read all active knowledge before questions. For the current personal KB, full-context retrieval avoids losing relevant details to top-k search. Embeddings are deferred and should be a derived index, never the sole canonical store. The explicit context cap must report an error instead of truncating records. `SCULPT_KNOWLEDGE_DIR` allows a future durable hosted mount; free Render storage is ephemeral.
- `guided_service.py` runs background jobs and saves each run at `output/tailored/<run-id>/guided.json`, including its evidence snapshot and explicit review decisions. Refresh resumes; server restarts expose interrupted jobs for retry. Proposals, attempts and PDF logs are isolated by run/generation. Master/rule changes require a new run; knowledge edits require evidence rechecking before finalization.
- Review selection/order and every changed field or omitted bullet together. Pending proposals appear only in the clearly labelled proposal PDF. The final build requires all decisions, no unresolved factual findings or unchecked edits, and verifies rendered layout locally without another full AI audit. Post-review fit failures must return for selected passage correction and renewed review; never silently modify approved text. Final YAML is saved separately under `content/tailored/`, PDF under the run's `final/` directory. Never overwrite the master PDF.
- The `.env` key stays server-side. SoCLaaS uses verified TLS with the macOS `/etc/ssl/cert.pem` bundle when available; never disable verification. `--jd` CLI automation is not implemented.
- Regression suite: `.venv/bin/python -m unittest discover -s tests -v`. Run real PDF and browser checks when changing fit or UI behavior, and live-model checks for prompt changes when service access is available.
