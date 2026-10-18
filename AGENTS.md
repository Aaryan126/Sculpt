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
Web UI: `python web_server.py` then open `http://127.0.0.1:8000`

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
│   └── style_guide.md          # Soft AI rules (future tailoring step)
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

- Given a JD, propose a section order and select exactly five existing projects by stable ID. Select 3–4 existing bullets per work/project entry when available; keep every bullet from shorter source entries. Select existing summary sentences and skill categories. After structure approval, a separate AI call may propose bullet rewrites, descriptive project titles, and entry technology list changes, each linked to master source IDs. Never apply wording proposals before explicit per-item review.
- Save the result in a separate `content/tailored/<company_role>.yaml`; show content changes for review.
- Build it with `python build.py --profile tailored --content content/tailored/<company_role>.yaml` and inspect `output/tailored/<company_role>/resume.pdf`.
- The local web UI first parses a pasted JD into exactly three editable fields: company, job role, and a cleaned job description. It saves a structure proposal, accepts user adjustments, saves source-linked wording proposals and explicit decisions, then builds a separate run-specific YAML and PDF. Review state lives in `output/tailored/<run-id>/review.json` so a refresh can resume. The `.env` key stays server-side and must never be logged or returned to the browser.
- SoCLaaS requests use verified TLS with the macOS `/etc/ssl/cert.pem` bundle when available; never disable certificate verification to work around Python.org's missing default CA file.
- The AI selects existing project and bullet IDs, existing skill categories, and summary sentences. It may propose entry-specific wording based on source text, but project/experience identities, dates, degrees, placements, metrics, and shared layout rules stay anchored to the master. Review the PDF before use.
- `--jd` CLI automation is not implemented; the web UI provides the JD workflow.
