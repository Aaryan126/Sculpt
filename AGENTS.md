# Resume Tailor - Agent Context

## Project Overview

Command-line tool that separates resume **content** (structured YAML) from **layout** (fixed LaTeX template). AI tailors only content — never layout. Font: TeX Gyre Termes (metrically identical to Times New Roman, works with pdfLaTeX).

## Quick Start

```bash
cd /Users/aaryan/Desktop/Sculpt
source .venv/bin/activate
export PATH=/Library/TeX/texbin:$PATH
python build.py
```

Output: `output/resume.pdf` | LaTeX: `output/resume.tex`
Verbose: `python build.py -v`

## Environment Setup

- **Python 3.13.12** with venv at `.venv/`
- **Dependencies:** `python-docx`, `pyyaml`, `jinja2`
- **LaTeX:** TeX Live 2026 (BasicTeX), at `/Library/TeX/texbin/`
- **LaTeX compiler:** `pdflatex` (configured in `config/rules.yaml`)
- **PATH fix:** Always `export PATH=/Library/TeX/texbin:$PATH` before building (subprocess doesn't inherit interactive shell PATH)

## Directory Structure

```
resume-tailor/ (project root: /Users/aaryan/Desktop/Sculpt)
├── Master_Resume.docx          # Source Word doc — NEVER modify
├── content/
│   └── master.yaml             # Structured resume content (SOURCE OF TRUTH)
├── config/
│   ├── rules.yaml              # Hard rules (code-enforced layout/content limits)
│   └── style_guide.md          # Soft AI rules (future tailoring step)
├── templates/
│   └── resume.tex.j2           # Fixed LaTeX template (DO NOT modify without approval)
├── output/
│   ├── resume.tex              # Generated LaTeX
│   └── resume.pdf              # Final PDF
├── build.py                    # Main build script — read + modify
└── README.md                   # User documentation
```

## Architecture

```
Master_Resume.docx (read once) → content/master.yaml (source of truth)
                                   ↓
                              config/rules.yaml (layout rules)
                              templates/resume.tex.j2 (fixed template)
                                   ↓
                              build.py → output/resume.tex → pdflatex → resume.pdf
```

### Data Flow

1. **build.py** reads `content/master.yaml` (structured content) + `config/rules.yaml` (layout rules)
2. Renders `templates/resume.tex.j2` with Jinja2 placeholder replacement
3. Compiles LaTeX to PDF using `pdflatex`
4. Validates: page count, project count, overfull boxes → prints PASS/FAIL report

### build.py Functions (key entry points)

| Function | Purpose |
|---|---|
| `load_yaml(path)` | Load YAML config files |
| `el(text)` | Escape special LaTeX chars (`&`, `%`, `$`, `#`, `_`, `{`, `}`, `~`, `^`) |
| `build_education(entries, rules)` | Generate LaTeX for education section |
| `build_experience(entries, rules)` | Generate LaTeX for experience section |
| `build_projects(entries, rules)` | Generate LaTeX for projects section (respects max_projects_render) |
| `build_certifications(entries, rules)` | Generate LaTeX for certifications section |
| `build_skills(skills, rules)` | Generate LaTeX for skills section |
| `generate_section_order(rules, resume)` | Build content in order from rules.yaml |
| `render_latex(rules, resume)` | Full template rendering with placeholder substitution |
| `compile_latex(tex_path, compiler_path)` | Run pdflatex twice |
| `get_pdf_page_count(pdf_path)` | Use `pdfinfo` to count pages |
| `validate(rules, tex_content)` | Print PASS/FAIL report |

## Config Files

### config/rules.yaml

All layout/content rules — edit to change output without touching code.

```yaml
layout:
  font: "TeX Gyre Termes"          # TeX Gyre Termes or Times New Roman
  font_size: "10pt"
  margins: {top: 0.5in, bottom: 0.5in, left: 0.6in, right: 0.6in}
  page_limit: 2
  max_projects: 7
  max_bullet_lines: 2
  section_order: [education, experience, projects, skills]
  compiler: "pdflatex"             # pdflatex, xelatex, or lualatex
  page_size: "letterpaper"

content:
  max_projects_render: 7           # 0 = all, N = first N projects
  max_bullets_per_entry: 4         # 0 = unlimited
```

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
  - name, competition, placement, tech, dates, bullets: [{id, text, tags}], tags: [...]

skills:
  programming: [...], frameworks_tools: [...], languages: [...]
```

Each bullet has a **stable ID** (e.g., `proj1-b1`, `exp1-b3`, `proj7-b2`) for AI tailoring references.

### Templates

**`templates/resume.tex.j2`** — LaTeX template with these placeholders:
- `LAYOUT_MARGINS`, `LAYOUT_PAGESIZE` — from rules.yaml
- `RESUME_NAME`, `RESUME_EMAIL`, `RESUME_PHONE`, `RESUME_GITHUB`, `RESUME_LINKEDIN`, `RESUME_SEEKING`
- `RESUME_SUMMARY`
- `SECTION_ORDER` — filled by build.py functions

Template uses:
- `mathptmx` (TeX Gyre Termes, Times-compatible)
- `tabular*` for left-aligned bold + right-aligned date layout
- `titlesec` with `[\titlerule]` for section heading underlines
- Compact `itemize` lists, `\linespread{0.95}` for tight line spacing

## Critical Rules for Agents

1. **NEVER modify `Master_Resume.docx`** — it's the source artifact only
2. **NEVER modify `templates/resume.tex.j2` without explicit approval** — layout is frozen
3. **Always escape LaTeX special characters** — use `el()` function, not raw strings
4. **All spacing/layout is in `rules.yaml`** — don't hardcode vspace or margins
5. **Use `pdfinfo` for page count** (not binary parsing — PDFs are compressed)
6. **LaTeX compiler is at `/Library/TeX/texbin/`** — always resolve full path in subprocess calls
7. **Run `pdflatex` twice** to resolve references/citations
8. **Content changes only via `master.yaml`** — bullets have stable IDs
9. **After any content/layout change, run `python build.py` and verify all checks PASS**

## Current State (Checkpoint)

- Baseline PDF builds: 2 pages, all validation checks PASS, no overfull boxes
- All 7 projects, 4 bullets max per entry, all verbatim content from Word doc
- Section structure: Education → Experience → Projects → Skills → Virtual Training
- Section headings have horizontal underline bars
- Header uses tabular* for left (bold) / right (date) alignment
- Experience tech list is `\textnormal{}` (not bold)
- Each project: header line → "Project: NAME" line → bullets
- Skills: each category on its own line

## Next Phase (Step 8 — Not Built Yet)

AI tailoring: `python build.py --jd jd.txt`
- AI reads master.yaml + rules.yaml + style_guide.md
- Returns structured selection: which projects, rewritten bullets, skill emphasis
- Code validates against rules.yaml
- Produces diff for review (never invent facts/metrics)
