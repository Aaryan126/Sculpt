#!/usr/bin/env python3
"""
build.py - Render resume.yaml + rules.yaml -> resume.tex -> resume.pdf
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent
CONTENT_DIR = PROJECT_ROOT / "content"
CONFIG_DIR = PROJECT_ROOT / "config"
TEMPLATE_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output"

MASTER_YAML = CONTENT_DIR / "master.yaml"
RULES_YAML = CONFIG_DIR / "rules.yaml"
TEMPLATE_FILE = TEMPLATE_DIR / "resume.tex.j2"

# Template for an entry header line (left-aligned bold + right-aligned date)
# Uses parbox for compact layout
_HEADER_FMT = (
    r"\noindent"
    r"\begin{{tabular*}}{{\textwidth}}"
    r"{{@{{}}l@{{\extracolsep{{\fill}}}}r@{{}}}}"
    r"  {left} & {right} \\\\"
    r"\end{{tabular*}}"
)

# Sub-project line: "Project: NAME" or "Module Project: NAME"
_SUBPROJECT_FMT = r"\noindent\textit{{{label}: {desc}}}"


def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def el(text):
    """Escape special LaTeX characters."""
    if not text:
        return ""
    for char, esc in [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
        ("×", r"\texttimes{}"),
        ("·", r"\textperiodcentered{}"),
    ]:
        text = text.replace(char, esc)
    return text


def build_education(entries, rules, certifications=None):
    lines = []
    lines.append(r"\section*{EDUCATION}")
    lines.append(r"\vspace{2pt}")

    for edu in entries:
        inst = el(edu.get("institution", ""))
        dates = el(edu.get("dates", ""))
        degree = el(edu.get("degree", ""))

        # Match the Word document: institution/date header, followed by one
        # bulleted paragraph per detail. Keep the parenthetical abbreviation
        # in regular weight, as it is in the source document.
        match = re.match(r"^(.*?)(\s*\([^()]+\))$", inst)
        if match:
            institution_name = r"\textbf{" + match.group(1).strip() + r"}" + el(match.group(2))
        else:
            institution_name = r"\textbf{" + inst + r"}"
        lines.append(_HEADER_FMT.format(left=institution_name, right=dates))
        lines.append(r"\vspace{-15pt}")

        details = [degree]
        if edu.get("specialisation"):
            details.append("Specialisation: " + el(edu["specialisation"]))
        if edu.get("honours") or edu.get("gpa"):
            honours_gpa = " ".join(
                el(edu[key]) for key in ("honours", "gpa") if edu.get(key)
            )
            details.append(honours_gpa)
        if edu.get("modules"):
            italic_indices = set(edu.get("italic_module_indices", []))
            rendered_modules = []
            for index, module in enumerate(edu["modules"]):
                # master.yaml stores each module as "(n) Title [details]".
                parsed = re.match(r"^(\(\d+\)\s*)(.*?)(\s*\[.*\])?$", module)
                if parsed:
                    prefix, title, details_text = parsed.groups()
                    title_tex = el(title)
                    if index in italic_indices:
                        title_tex = r"\textit{" + title_tex + "}"
                    rendered_modules.append(
                        el(prefix) + title_tex + el(details_text or "")
                    )
                else:
                    rendered_modules.append(el(module))
            details.append("Relevant Modules: " + " ".join(rendered_modules))

        lines.append(r"\begin{itemize}")
        for detail in details:
            lines.append(r"  \item " + detail)
        lines.append(r"\end{itemize}")
        lines.append(r"\vspace{2pt}")

    # The source Word document places this subsection directly after education.
    lines.append(r"\textbf{Virtual Training and Learning \& Development}")
    lines.append(r"\begin{itemize}")
    for cert in certifications or []:
        title = cert.get("title", "")
        if ": " in title:
            label, credential = title.split(": ", 1)
            rendered = el(label + ": ") + r"\textit{" + el(credential) + "}"
        else:
            rendered = el(title)
        lines.append(r"  \item " + rendered)
    lines.append(r"\end{itemize}")

    return "\n".join(lines)


def build_experience(entries, rules):
    lines = []
    lines.append(r"\section*{WORK EXPERIENCE}")
    lines.append(r"\vspace{2pt}")

    for exp in entries:
        company = el(exp.get("company", ""))
        role = el(exp.get("role", ""))
        tech = el(exp.get("tech", ""))
        dates = el(exp.get("dates", ""))

        # Left cell: bold company, role then normal pipe + tech, all in one cell
        # The company and role are bold; tech is outside \textbf{}
        left = r"\textbf{" + company + r", " + role + r"}"
        if tech:
            left += r"\textnormal{\hspace{0.3em}\textbar{}\hspace{0.3em}" + tech + r"}"

        lines.append(_HEADER_FMT.format(left=left, right=dates))
        lines.append(r"\vspace{-15pt}")

        if exp.get("bullets"):
            lines.append(r"\begin{itemize}")
            for bullet in exp["bullets"]:
                text = el(bullet.get("text", "").strip())
                lines.append(r"  \item " + text)
            lines.append(r"\end{itemize}")
            lines.append(r"\vspace{2pt}")

    return "\n".join(lines)


def build_projects(entries, rules):
    max_p = rules.get("content", {}).get("max_projects_render", 0)
    if max_p and max_p > 0:
        entries = entries[:max_p]
    intro_min_lines = rules.get("layout", {}).get("project_intro_min_lines", 6)
    if not isinstance(intro_min_lines, int) or intro_min_lines < 1:
        raise ValueError("layout.project_intro_min_lines must be a positive integer")

    lines = []
    lines.append(r"\section*{ACADEMIC PROJECTS / COMPETITION PROJECT / RESEARCH EXPERIENCE}")
    lines.append(r"\vspace{2pt}")

    for proj in entries:
        name = el(proj.get("name", ""))
        competition = el(proj.get("competition", ""))
        placement = el(proj.get("placement", ""))
        tech = el(proj.get("tech", ""))
        dates = el(proj.get("dates", ""))

        # Entry header: competition + placement on left, tech on right of pipe, date on far right
        left = r"\textbf{" + competition
        if placement:
            left += " – " + placement
        left = left + r"}"
        if tech:
            left += r"\textnormal{\hspace{0.3em}\textbar{}\hspace{0.3em}" + tech + r"}"

        lines.append(r"\keepentryintro{" + str(intro_min_lines) + "}")
        lines.append(_HEADER_FMT.format(left=left, right=dates))
        lines.append(r"\nopagebreak")
        lines.append(r"\par\vspace{-16pt}")

        # Project description line (italic)
        desc = el(proj.get("name", ""))
        label = el(proj.get("project_label", "Project"))
        lines.append(_SUBPROJECT_FMT.format(label=label, desc=desc))
        lines.append(r"\nopagebreak")
        lines.append(r"\par\vspace{3pt}")

        if proj.get("bullets"):
            lines.append(r"\begin{itemize}")
            for bullet in proj["bullets"]:
                text = el(bullet.get("text", "").strip())
                lines.append(r"  \item " + text)
            lines.append(r"\end{itemize}")
        lines.append(r"\vspace{4pt}")

    return "\n".join(lines)


def build_certifications(entries, rules):
    lines = []
    lines.append(r"\section*{VIRTUAL TRAINING AND LEARNING \& DEVELOPMENT}")
    lines.append(r"\vspace{2pt}")

    for cert in entries:
        title = el(cert.get("title", ""))
        lines.append(title)
        lines.append(r"\vspace{2pt}")

    return "\n".join(lines)


def build_skills(skills, rules):
    lines = []
    lines.append(r"\section*{SKILLS}")
    lines.append(r"\vspace{2pt}")
    lines.append(r"\begin{itemize}")

    for label, items in skills.items():
        if items:
            values = ", ".join(el(item) for item in items)
            lines.append(r"  \item \textbf{" + el(label) + r":} " + values)

    lines.append(r"\end{itemize}")
    lines.append(r"\vspace{4pt}")
    return "\n".join(lines)


def generate_section_order(rules, resume):
    section_map = {
        "education": build_education,
        "experience": build_experience,
        "projects": build_projects,
        "skills": build_skills,
    }

    section_order = rules.get("layout", {}).get("section_order", [])
    sections = []
    for key in section_order:
        if key in section_map and key in resume:
            data = resume[key]
            if data:
                if key == "education":
                    sections.append(build_education(data, rules, resume.get("certifications", [])))
                else:
                    sections.append(section_map[key](data, rules))

    return "\n".join(sections)


def render_latex(rules, resume):
    with open(TEMPLATE_FILE, "r") as f:
        template_content = f.read()

    margins = rules.get("layout", {}).get("margins", {})
    margin_str = ", ".join(side + "=" + margins[side] for side in ["top", "bottom", "left", "right"])

    sections = generate_section_order(rules, resume)

    result = template_content
    result = result.replace("LAYOUT_MARGINS", margin_str)
    result = result.replace("LAYOUT_PAGESIZE", rules.get("layout", {}).get("page_size", "letterpaper"))
    result = result.replace("RESUME_NAME", el(resume.get("contact", {}).get("name", "Resume")))
    result = result.replace("RESUME_EMAIL", el(resume.get("contact", {}).get("email", "")))
    result = result.replace("RESUME_PHONE", el(resume.get("contact", {}).get("phone", "")))
    result = result.replace("RESUME_GITHUB_URL", resume.get("contact", {}).get("github", ""))
    result = result.replace("RESUME_LINKEDIN_URL", resume.get("contact", {}).get("linkedin", ""))
    result = result.replace("RESUME_SEEKING", el(resume.get("contact", {}).get("seeking", "")))
    result = result.replace("RESUME_SUMMARY", el(resume.get("summary", "")))
    result = result.replace("SECTION_ORDER", sections)

    return result


def compile_latex(tex_path, compiler_path):
    for _ in range(2):
        result = subprocess.run(
            [compiler_path, "-interaction=nonstopmode", str(tex_path)],
            capture_output=True, text=True, cwd=str(tex_path.parent),
        )
        if result.returncode != 0 and "Error" in result.stderr:
            errors = result.stderr.strip().split("\n")
            for line in errors[-30:]:
                if any(kw in line for kw in ["Error", "Missing", "Undefined", "Overfull", "Underfull"]):
                    print("  " + line)
            print()

    subprocess.run(
        [compiler_path, "-interaction=nonstopmode", str(tex_path)],
        capture_output=True, text=True, cwd=str(tex_path.parent),
    )


def get_pdf_page_count(pdf_path):
    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True, text=True,
        )
        for line in result.stdout.split("\n"):
            if line.strip().startswith("Pages:"):
                return int(line.strip().split(":")[1].strip())
    except Exception:
        pass
    return -1


def validate(rules, tex_content):
    page_limit = rules.get("layout", {}).get("page_limit", 2)
    max_projects = rules.get("layout", {}).get("max_projects", 5)

    pdf_path = OUTPUT_DIR / "resume.pdf"

    # Page count
    page_count = get_pdf_page_count(pdf_path)
    if page_count <= page_limit:
        print("  [PASS] Page count: {}/{} (limit)".format(page_count, page_limit))
    else:
        print("  [FAIL] Page count: {}/{} (limit) - EXCEEDS LIMIT".format(page_count, page_limit))

    # Project count
    project_count = len(re.findall(r"ACADEMIC PROJECTS", tex_content))
    if project_count <= max_projects:
        print("  [PASS] Project sections: {}/{} (limit)".format(project_count, max_projects))
    else:
        print("  [FAIL] Project sections: {}/{} (limit) - EXCEEDS LIMIT".format(project_count, max_projects))

    # Overfull boxes
    tex_log = OUTPUT_DIR / "resume.log"
    if tex_log.exists():
        with open(tex_log) as f:
            log_content = f.read()
        ov = len(re.findall(r"! ?Overfull \\vbox", log_content))
        oh = len(re.findall(r"! ?Overfull \\hbox", log_content))
        if ov or oh:
            print("  [WARN] Overfull boxes: {} vbox, {} hbox".format(ov, oh))
        else:
            print("  [PASS] No overfull boxes")
    else:
        print("  [SKIP] No .log file found")

    print()


def find_compiler(compiler_name):
    for candidate in [compiler_name,
                      "/Library/TeX/texbin/" + compiler_name,
                      "/usr/local/texlive/" + compiler_name,
                      "/usr/bin/" + compiler_name]:
        if subprocess.run(["which", candidate], capture_output=True).returncode == 0:
            return candidate
    return None


def main():
    parser = argparse.ArgumentParser(description="Build resume from YAML + rules -> PDF")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show compiled LaTeX")
    args = parser.parse_args()

    print("[1/5] Loading configuration...")
    try:
        rules = load_yaml(RULES_YAML)
        resume = load_yaml(MASTER_YAML)
    except Exception as e:
        print("Error loading YAML files: {}".format(e))
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[2/5] Rendering LaTeX template...")
    tex_content = render_latex(rules, resume)

    tex_path = OUTPUT_DIR / "resume.tex"
    with open(tex_path, "w") as f:
        f.write(tex_content)

    if args.verbose:
        print("\n" + tex_content)

    compiler_name = rules.get("layout", {}).get("compiler", "pdflatex")
    compiler_path = find_compiler(compiler_name)
    if not compiler_path:
        print("[FAIL] Could not find LaTeX compiler: " + compiler_name)
        sys.exit(1)

    print("[3/5] Compiling with {}...".format(compiler_path))
    compile_latex(tex_path, compiler_path)

    pdf_path = OUTPUT_DIR / "resume.pdf"
    if not pdf_path.exists():
        print("[FAIL] PDF was not generated. Check output/resume.log for errors.")
        sys.exit(1)

    print("[4/5] Validation:")
    validate(rules, tex_content)

    print("[5/5] Done!")
    print("  PDF:    {}".format(pdf_path))
    print("  LaTeX:  {}".format(tex_path))
    print()


if __name__ == "__main__":
    main()
