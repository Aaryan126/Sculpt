# Resume Tailor

Content-driven resume generation. Resume text lives in YAML; approved layout rules live in `config/rules.yaml`.

## Quick Start

```bash
cd /Users/aaryan/Desktop/Sculpt
python3 -m venv .venv && source .venv/bin/activate
pip install python-docx pyyaml jinja2
export PATH=/Library/TeX/texbin:$PATH
python build.py
```

The default command builds the master resume at `output/resume.pdf` and `output/resume.tex`. The build needs `pdflatex`, `pdfinfo`, and `pdftohtml` on `PATH`.

Run with `-v` to see the generated LaTeX.

## Project Structure

```
resume-tailor/
├── Master_Resume.docx        # Source Word doc (never modified by the tool)
├── content/
│   ├── master.yaml           # Structured resume content (your source of truth)
│   └── tailored/             # Separate per-job YAML files, created when needed
├── config/
│   ├── rules.yaml            # Hard layout rules (code-enforced)
│   ├── profiles/tailored.yaml # Tailored-only rule overrides
│   └── style_guide.md        # Soft AI style rules
├── templates/
│   └── resume.tex.j2         # Fixed LaTeX template
├── output/
│   ├── resume.tex            # Generated LaTeX
│   └── resume.pdf            # Final resume PDF
├── build.py                  # Render and compile
├── pdf_checks.py             # Check rendered PDF lines, styles, and page breaks
├── tailor.py                 # SoCLaaS selection and safe content assembly
├── review_flow.py            # Source-linked wording suggestions and approval application
├── web_server.py             # Local JD form and PDF preview server
├── web/                      # HTML, CSS, and browser JavaScript
└── README.md                 # This file
```

## Editing Rules

### config/rules.yaml (hard rules)

| Rule | Default | Description |
|------|---------|-------------|
| `layout.font` | Nimbus Roman No9 L | Embedded Times-style font via `mathptmx` |
| `layout.font_size`, `name_font_size` | 10pt, 14pt | Body and name sizes |
| `layout.margins.*` | 0.5in top/bottom, 0.6in sides | Page margins |
| `layout.page_limit` | 2 | Maximum pages |
| `layout.max_bullet_lines` | 3 | Maximum rendered lines for work, project, and skills bullets |
| `layout.header_lines`, `max_summary_lines` | 3, 4 | Header and summary line limits |
| `layout.max_project_heading_lines`, `max_project_title_lines` | 1, 1 | Project heading and italic title line limits |
| `layout.project_intro_min_lines` | 6 | Keep a project heading with its title and first bullet |
| `layout.overfull_tolerance_pt` | 3 | Warn within tolerance, fail above it |
| `layout.styles`, `layout.spacing` | Current PDF appearance | Font styles and layout distances |
| `layout.section_order` | experience, education, projects, skills | Master default; reviewed tailored runs may reorder the first three |
| `layout.compiler` | pdflatex | LaTeX engine |
| `content.max_bullets_per_entry` | 4 | Max bullets per project or work entry |

The master profile has no project-count cap. The tailored profile inherits the same typography and spacing and requires exactly 5 projects. A tailored run may put Work Experience, Education, and Projects in a reviewed role-specific order; Skills stays last. Each work or project entry normally needs 3–4 bullets; if its master entry has only 2 or 3, the tailored version must retain all of them. The AI prefers 4 relevant bullets when available. The builder checks the finished PDF and exits with a failure that names the entry and exact text when a hard rule is broken. It never pads bullets or changes font size to force a pass. The current master BOLDR bullet produces a 2.154pt overfull warning, within the approved 3pt tolerance.

### config/style_guide.md (soft rules)

For the AI tailoring step (future). Contains recommendations for bullet quality, prioritization, tone, and truthfulness.

## Editing Content

Edit `content/master.yaml` only when changing the master resume. Each project has a stable ID (e.g., `proj1`); each bullet has a stable ID (e.g., `proj1-b1`) and optional tags. The Word doc is never touched — it was only used to create master.yaml.

## Tailored resumes

For each job description, make a separate content file under `content/tailored/` based on the master YAML. The web workflow proposes a section order and selects exactly 5 existing projects, source-aware bullet counts, existing summary sentences, and existing skill categories. After you approve that plan, a separate AI pass may suggest revised bullet wording, project descriptive titles, and entry technology lists. Each suggestion displays the master wording and supporting master IDs; it enters the PDF only after you accept or edit it. Keep the master file intact. Build the tailored file with:

```bash
python build.py --profile tailored --content content/tailored/company_role.yaml
```

The output goes to `output/tailored/company_role/resume.pdf` and `.tex`; use `--output-dir` to choose a different tailored destination. Fewer or more than five projects causes an explicit failure listing the selected projects, with no silent truncation or padding. The build also rejects missing, duplicate, or unknown project IDs and work/project entries outside their source-aware bullet limits.

## Local web UI

Put your real SoCLaaS key in the ignored `.env` file, replacing `apikey`. The URL and model are already set:

```dotenv
SOCLAAS_BASE_URL=https://soclaas-api.comp.nus.edu.sg/v1
SOCLAAS_API_KEY="your-real-key"
SOCLAAS_MODEL=qwen3.6:35b
SOCLAAS_TIMEOUT_SECONDS=300
```

Start the local server and open `http://127.0.0.1:8000`:

```bash
source .venv/bin/activate
export PATH=/Library/TeX/texbin:$PATH
python web_server.py
```

Paste a JD and select **Parse job posting**. The first AI step extracts the company and job role, then cleans LinkedIn page clutter from the remaining posting while keeping its substantive details together in one job description field. Review or edit these three fields, then request a structure plan. Review the proposed section order, five projects, bullets, skill categories, and summary sentences. Approve or adjust the plan to request wording suggestions. The wording board groups proposed edits by work entry or project, shows changed words and source evidence, and tracks pending and completed decisions. For each edit choose **Accept**, **Keep master wording**, **Use my edit**, or **Suggest another version**. **Preview current draft PDF** builds from current decisions while pending suggestions retain master wording; the final PDF requires a decision on every suggestion. The app saves the draft and decisions locally per run so a refresh can resume review. Review the final PDF before using it.

Each run saves review state at `output/tailored/<run-id>/review.json`. Once built, it also saves `content/tailored/<run-id>.yaml`, `output/tailored/<run-id>/parsed_jd.json`, and `output/tailored/<run-id>/resume.pdf`. Both directories and `.env` are ignored by Git. The API key stays on the Python server and is never sent to the browser. Python loads the macOS system certificate bundle for SoCLaaS while keeping TLS verification enabled. The CLI `--jd` flag is still not implemented; the web UI provides the JD workflow.
