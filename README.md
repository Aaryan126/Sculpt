# Resume Tailor

Content-driven resume generation. AI edits YAML content only; layout lives in a fixed LaTeX template.

## Quick Start

```bash
cd resume-tailor
python3 -m venv .venv && source .venv/bin/activate
pip install python-docx pyyaml jinja2
export PATH=/Library/TeX/texbin:$PATH
python build.py
```

Output: `output/resume.pdf`

Run with `-v` to see the generated LaTeX.

## Project Structure

```
resume-tailor/
├── Master_Resume.docx        # Source Word doc (never modified by the tool)
├── content/
│   └── master.yaml           # Structured resume content (your source of truth)
├── config/
│   ├── rules.yaml            # Hard layout rules (code-enforced)
│   └── style_guide.md        # Soft AI style rules
├── templates/
│   └── resume.tex.j2         # Fixed LaTeX template
├── output/
│   ├── resume.tex            # Generated LaTeX
│   └── resume.pdf            # Final resume PDF
├── build.py                  # Run this to build
└── README.md                 # This file
```

## Editing Rules

### config/rules.yaml (hard rules)

| Rule | Default | Description |
|------|---------|-------------|
| `layout.font` | TeX Gyre Termes | Font family (Termes or Times New Roman) |
| `layout.font_size` | 11pt | Document font size |
| `layout.margins.*` | 0.6-0.7in | Page margins |
| `layout.page_limit` | 2 | Maximum pages |
| `layout.max_projects` | 5 | Maximum projects shown |
| `layout.max_bullet_lines` | 2 | Target max bullet lines in PDF |
| `layout.section_order` | edu,exp,proj,skills | Section display order |
| `layout.compiler` | pdflatex | LaTeX engine |
| `content.max_projects_render` | 5 | Projects included in render |
| `content.max_bullets_per_entry` | 3 | Max bullets per project/experience |

### config/style_guide.md (soft rules)

For the AI tailoring step (future). Contains recommendations for bullet quality, prioritization, tone, and truthfulness.

## Editing Content

Edit `content/master.yaml` directly. Each bullet has a stable ID (e.g., `proj1-b1`) and optional tags. The Word doc is never touched — it was only used to create master.yaml.

## AI Tailoring (Future)

```bash
python build.py --jd job_description.txt
```

AI will return a structured selection of projects, rewritten bullets, and skill emphasis. Code validates against rules.yaml and produces a diff for review.
