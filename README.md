# Resume Tailor

Content-driven resume generation. Resume text lives in YAML; approved layout rules live in `config/rules.yaml`.

## Quick Start

Launch the web app from any directory using the existing project environment:

```bash
/Users/aaryan/Desktop/Sculpt/run.sh
```

Open `http://127.0.0.1:8000`. Stop the server with **Ctrl+C**. From the project directory, `./run.sh` also works. The launcher uses `.venv` and sets the LaTeX path automatically; server options pass through, for example `./run.sh --port 8001`.

For first-time environment setup and a standalone master PDF build:

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
├── review_flow.py            # Legacy wording review
├── guided_tailoring.py       # Requirements, whole-resume drafting, claim audit and PDF fit
├── staged_generation.py      # Shared resume plan, small writing/audit requests and checkpoints
├── guided_service.py         # Saved runs, decisions and background jobs
├── knowledge.py              # Atomic human-readable knowledge storage
├── knowledge/                # Private knowledge.json and revision history
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

Contains recommendations for bullet quality, prioritization, tone, and truthfulness. The guided drafting contract additionally enforces source attribution and explicit review.

## Editing Content

Edit `content/master.yaml` only when changing the master resume. Each project has a stable ID (e.g., `proj1`); each bullet has a stable ID (e.g., `proj1-b1`) and optional tags. The Word doc is never touched — it was only used to create master.yaml.

## Tailored resumes

The guided workflow reads the complete JD, master resume, and active saved knowledge. It maps substantive requirements to evidence, distinguishes supported experience from transferable experience and gaps, and asks up to four useful questions. The model can synthesize and substantially reframe facts within an experience or project, including the summary, bullets, descriptive titles, technology lists, and individual skills. Official identities, dates, education, placements and contact details remain anchored to the master.

Requirement analysis selects numbered passages from the confirmed JD. The app copies the original passage into each requirement, so quotations do not depend on the model reproducing punctuation or wording. Invalid passage references are rejected and returned for correction.

The JD guides relevance; it cannot establish facts about your experience. Proposed future projects stay in recommendations and never become completed accomplishments. Every proposed field cites evidence. Numeric and entry-attribution checks run in code, followed by an AI claim audit. AI audits are fallible; explicit human review remains required.

The model reads the layout rules before drafting. It then renders the actual PDF and gets up to two repair attempts for specific claim or layout failures. No font or spacing rules are relaxed. A failed fit reports the offending content instead of silently dropping it. Build any separate tailored YAML manually with:

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
/Users/aaryan/Desktop/Sculpt/run.sh
```

The interface focuses on one active step: **paste JD → confirm job details → answer useful questions → review the resume → final PDF**. There is no navigation sidebar. Role analysis, source evidence, recommendations and refinement controls expand on demand. The master and proposal PDFs open only when requested.

1. **Analyze:** read all active knowledge before asking questions. Requirements include exact passages from the JD; there is no keyword similarity or screening probability score.
2. **Answer:** save exact questions and answers to local JSON before starting generation. Mark information as confirmed experience, a limitation, uncertain, or planned. Blank answers can be skipped. Unsent answers are recovered in the same browser.
3. **Draft first:** one holistic writing request produces a complete draft. It is saved and visible before the evidence check finishes. Unchanged fields retain their original text; the model can substantially rewrite any supported field.
4. **Review:** one evidence check attaches factual concerns and optional editorial suggestions to passages. Read the complete draft or preview its PDF while checking runs. Accepting a proposal does not waive factual concerns: keep the original, edit and recheck, or explicitly confirm every claim in the displayed passage. Confirmed passages are saved to knowledge with the correct work/project scope.
5. **Correct and finish:** **Correct this passage** or **Correct selected passages** changes only the selected fields, then checks those changes. Unrelated decisions stay intact. **Check edited passages** checks manual edits and refreshes the PDF. Export requires explicit decisions, no unresolved factual concerns, current evidence checks, and passing physical PDF limits. Suggestions never block export. Final export compiles and checks the approved content locally; it does not run another full AI audit or silently rewrite it.

**Knowledge** in the header lets you add, edit, archive and export information. The canonical file is `knowledge/knowledge.json`, created on first save, with prior versions in `knowledge/history/`. You can edit it directly while the server is idle; see [the format and examples](knowledge/README.md). Knowledge changes after drafting require a fresh evidence check before finalization. Questions ask one specific thing at a time; bare yes/no answers are preserved but treated as uncertain evidence, not proof of multiple accomplishments. For this personal KB, the model reads every active entry rather than relying on embeddings or a top-k filter; a size limit fails explicitly without silently discarding evidence. Embeddings can later be added as a derived retrieval index.

Each guided run saves its evidence snapshot, requirements, exact answers, draft and review decisions in `output/tailored/<run-id>/guided.json`. Proposal attempts and validation logs live under that run's `proposals/` directory; reviewed PDFs live under `final/`. A successful final build also saves `content/tailored/<run-id>.yaml`. The browser remembers the active run ID; starting a new resume retains saved knowledge. A server restart preserves local runs and makes interrupted jobs retryable. Older runs remain accessible through `/legacy` using the previous review workflow.

The normal generation path has two main model calls: one writer and one checker. There is no automatic three-pass rewrite loop. A malformed schema gets at most one correction request. Transport failures leave a visible saved draft when one exists; **Resume evidence check** never regenerates it. Completed checks are tied to exact passage text and source IDs. Corrections invalidate only changed checks. Explicit factual confirmation can resolve a missing-source concern without another model call.

Existing failed guided runs containing a full candidate in `attempts.json` can recover that candidate on **Resume draft**, then use the new check/review flow. No legacy approvals are inferred. New drafts are checkpointed in `draft.json`, evidence/PDF results under `review-checks/`, and selected repairs under `repairs/`. The master resume, fixed template and layout limits remain unchanged.

Responses stream from SoCLaaS, with elapsed progress updates during generation. `SOCLAAS_TIMEOUT_SECONDS` is a connection/read-inactivity timeout (30–600 seconds; default 300), not a five-minute total generation limit: an active stream can run longer. Reasoning content is neither displayed nor logged. Incomplete streams are rejected rather than treated as finished drafts.

Model calls can still take time or fail when the provider is busy. Provider/network failures stop the task instead of triggering content rewrites. New full candidates are checkpointed in `draft.json`; validated model responses live in `calls/` subdirectories. Historical `attempts.json` files are retained for recovery. Retry interrupted tasks explicitly. The provider can still impose its own request limits.

Knowledge, generated runs, and `.env` are ignored by Git. The API key stays on the Python server; TLS verification stays enabled. The CLI `--jd` flag is not implemented. Local persistence is implemented first; no durable hosted database or embedding service is required.

Run the regression suite with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The tests cover persistence, manual edits and conflicts, complete knowledge retrieval, evidence restrictions, bounded repairs, explicit review, and restart recovery. They use model stubs; live model quality and PDF/browser integration should be checked separately when changing the prompts or UI.

## Render deployment

The frontend, Python API, and PDF builder deploy together as one **free Render web service**. `Dockerfile` installs LaTeX and Poppler, builds the master PDF, and starts the same web server used locally. `render.yaml` defines the service and prompts for the two secrets. No Vercel or Netlify project is needed.

After these files are pushed to GitHub, use [Deploy to Render](https://render.com/deploy?repo=https://github.com/Aaryan126/Sculpt) or follow the steps below.

1. Push this project to a GitHub repository you control. Keep the repository private if you do not want your master resume and contact details public. `.env` is ignored by Git and excluded from the Docker build context; never commit it.
2. In Render, choose **New → Blueprint**, connect the repository, and select `render.yaml`.
3. When prompted, enter `SOCLAAS_API_KEY` and a unique `RESUME_ACCESS_PASSWORD` of at least 20 characters. Render stores them as service environment variables. The login username is `resume`. You can generate a password locally with `openssl rand -base64 32` and save it in your password manager.
4. Approve the Blueprint deployment. Open the resulting `https://...onrender.com` URL and sign in using the browser prompt. The password gate covers the UI, API, master PDF, saved reviews, and generated PDFs. Render terminates HTTPS before forwarding requests to the app.

The server listens on Render's `PORT` and refuses to bind to a non-local address without the access password. The `SOCLAAS_BASE_URL` and model are set in `render.yaml`; the API key is supplied only in Render. The Blueprint disables automatic redeploys; deploy manually from Render after future code changes.

**Free-tier limits:** Render sleeps the service after 15 minutes without an incoming request and may restart it. Its free filesystem is temporary, so saved knowledge, unfinished reviews, tailored YAML, and generated PDFs can disappear on sleep, restart, or redeploy. Finish a review and download its PDF before leaving. For durable hosted knowledge, mount persistent storage and set `SCULPT_KNOWLEDGE_DIR` to that directory. This setting only covers knowledge; run files and final outputs still need their own durable storage or a future storage adapter. This version is intended for local persistence first. Initial startup after sleep can take around a minute. The free instance has 512 MB RAM; the Docker build and PDF generation need to complete within that limit. SoCLaaS also needs to accept requests from Render's network, which can only be confirmed after deployment.

For local use, continue running `python web_server.py`; the browser password prompt is enabled only when `RESUME_ACCESS_PASSWORD` is set. If you manually bind the server to a non-local address, it requires a password of at least 20 characters.
