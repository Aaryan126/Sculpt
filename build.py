#!/usr/bin/env python3
"""
build.py - Render content/master.yaml + config/rules.yaml -> resume.tex -> resume.pdf
"""

import argparse
from copy import deepcopy
import re
import subprocess
import sys
from pathlib import Path

import yaml

from pdf_checks import check_overfull, check_rendered_pdf

PROJECT_ROOT = Path(__file__).parent
CONTENT_DIR = PROJECT_ROOT / "content"
CONFIG_DIR = PROJECT_ROOT / "config"
TEMPLATE_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output"

MASTER_YAML = CONTENT_DIR / "master.yaml"
RULES_YAML = CONFIG_DIR / "rules.yaml"
TAILORED_RULES_YAML = CONFIG_DIR / "profiles" / "tailored.yaml"
TEMPLATE_FILE = TEMPLATE_DIR / "resume.tex.j2"

# Template for an entry header line (left-aligned bold + right-aligned date)
# Uses tabular* for compact layout
_HEADER_FMT = (
    r"\noindent"
    r"\begin{{tabular*}}{{\textwidth}}"
    r"{{@{{}}l@{{\extracolsep{{\fill}}}}r@{{}}}}"
    r"  {left} & {right} \\\\"
    r"\end{{tabular*}}"
)

def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def merge_rules(base, override):
    """Merge a small profile override without duplicating shared layout rules."""
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_rules(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


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


def spacing(rules, key):
    """Render a configured TeX distance without embedding layout values in content."""
    value = rules["layout"]["spacing"][key]
    if not isinstance(value, str) or not re.fullmatch(r"-?\d+(?:\.\d+)?(?:pt|em|in)", value):
        raise ValueError(f"layout.spacing.{key} must be a TeX distance, got {value!r}")
    return value


def vspace(rules, key):
    return r"\vspace{" + spacing(rules, key) + "}"


def styled(text, rules, key):
    style = rules["layout"]["styles"][key]
    if style == "bold":
        return r"\textbf{" + text + "}"
    if style == "italic":
        return r"\textit{" + text + "}"
    if style == "regular":
        return r"\textnormal{" + text + "}"
    raise ValueError(f"layout.styles.{key} has unsupported style {style!r}")


def build_education(entries, rules, certifications=None):
    lines = []
    lines.append(r"\section*{EDUCATION}")
    lines.append(vspace(rules, "section_content"))

    for edu in entries:
        inst = edu.get("institution", "")
        dates = styled(el(edu.get("dates", "")), rules, "dates")
        degree = el(edu.get("degree", ""))

        # Match the Word document: institution/date header, followed by one
        # bulleted paragraph per detail. Keep the parenthetical abbreviation
        # in regular weight, as it is in the source document.
        match = re.match(r"^(.*?)(\s*\([^()]+\))$", inst)
        if match:
            institution_name = styled(el(match.group(1).strip()), rules, "institution_name") + el(match.group(2))
        else:
            institution_name = styled(el(inst), rules, "institution_name")
        lines.append(_HEADER_FMT.format(left=institution_name, right=dates))
        lines.append(vspace(rules, "education_header_to_details"))

        details = [degree]
        if edu.get("specialisation"):
            details.append("Specialisation: " + el(edu["specialisation"]))
        if edu.get("honours") or edu.get("gpa"):
            honours_gpa = " ".join(
                el(edu[key]) for key in ("honours", "gpa") if edu.get(key)
            )
            details.append(honours_gpa)
        if edu.get("modules"):
            rendered_modules = []
            for module in edu["modules"]:
                # master.yaml stores each module as "(n) Title [details]".
                parsed = re.match(r"^(\(\d+\)\s*)(.*?)(\s*\[.*\])?$", module)
                if parsed:
                    prefix, title, details_text = parsed.groups()
                    title_tex = styled(el(title), rules, "module_title")
                    rendered_modules.append(
                        el(prefix) + title_tex + el(details_text or "")
                    )
                else:
                    rendered_modules.append(el(module))
            details.append("Relevant Modules: " + " ".join(rendered_modules))

        lines.append(r"\begin{itemize}")
        for detail in details:
            lines.append(r"  \item " + styled(detail, rules, "bullets"))
        lines.append(r"\end{itemize}")
        lines.append(vspace(rules, "education_entry_after"))

    # The source Word document places this subsection directly after education.
    lines.append(styled(r"Virtual Training and Learning \& Development", rules, "institution_name"))
    lines.append(r"\begin{itemize}")
    for cert in certifications or []:
        title = cert.get("title", "")
        if ": " in title:
            label, credential = title.split(": ", 1)
            rendered = el(label + ": ") + styled(el(credential), rules, "certification_name")
        else:
            rendered = el(title)
        lines.append(r"  \item " + styled(rendered, rules, "bullets"))
    lines.append(r"\end{itemize}")

    return "\n".join(lines)


def build_experience(entries, rules):
    lines = []
    lines.append(r"\section*{WORK EXPERIENCE}")
    lines.append(vspace(rules, "section_content"))

    for exp in entries:
        company = el(exp.get("company", ""))
        role = el(exp.get("role", ""))
        tech = el(exp.get("tech", ""))
        dates = styled(el(exp.get("dates", "")), rules, "dates")

        # Left cell: bold company, role then normal pipe + tech, all in one cell
        # The company and role are bold; tech is outside \textbf{}
        left = styled(company + r", " + role, rules, "work_heading")
        if tech:
            gap = spacing(rules, "technology_separator")
            left += styled(r"\hspace{" + gap + r"}\textbar{}\hspace{" + gap + "}" + tech, rules, "technologies")

        lines.append(_HEADER_FMT.format(left=left, right=dates))
        lines.append(vspace(rules, "work_header_to_bullets"))

        if exp.get("bullets"):
            lines.append(r"\begin{itemize}")
            for bullet in exp["bullets"]:
                text = el(bullet.get("text", "").strip())
                lines.append(r"  \item " + styled(text, rules, "bullets"))
            lines.append(r"\end{itemize}")
            lines.append(vspace(rules, "work_entry_after"))

    return "\n".join(lines)


def build_projects(entries, rules):
    intro_min_lines = rules.get("layout", {}).get("project_intro_min_lines", 6)
    if not isinstance(intro_min_lines, int) or intro_min_lines < 1:
        raise ValueError("layout.project_intro_min_lines must be a positive integer")

    lines = []
    lines.append(r"\section*{ACADEMIC PROJECTS / COMPETITION PROJECT / RESEARCH EXPERIENCE}")
    lines.append(vspace(rules, "section_content"))

    for proj in entries:
        competition = el(proj.get("competition", ""))
        placement = el(proj.get("placement", ""))
        tech = el(proj.get("tech", ""))
        dates = styled(el(proj.get("dates", "")), rules, "dates")

        # Entry header: competition + placement on left, tech on right of pipe, date on far right
        left = competition
        if placement:
            left += " – " + placement
        left = styled(left, rules, "project_heading")
        if tech:
            gap = spacing(rules, "technology_separator")
            left += styled(r"\hspace{" + gap + r"}\textbar{}\hspace{" + gap + "}" + tech, rules, "technologies")

        lines.append(r"\keepentryintro{" + str(intro_min_lines) + "}")
        lines.append(_HEADER_FMT.format(left=left, right=dates))
        lines.append(r"\nopagebreak")
        lines.append(r"\par" + vspace(rules, "project_header_to_title"))

        # Project description line (italic)
        desc = el(proj.get("name", ""))
        label = el(proj.get("project_label", "Project"))
        lines.append(r"\noindent" + styled(label + ": " + desc, rules, "project_title"))
        lines.append(r"\nopagebreak")
        lines.append(r"\par" + vspace(rules, "project_title_to_bullets"))

        if proj.get("bullets"):
            lines.append(r"\begin{itemize}")
            for bullet in proj["bullets"]:
                text = el(bullet.get("text", "").strip())
                lines.append(r"  \item " + styled(text, rules, "bullets"))
            lines.append(r"\end{itemize}")
        lines.append(vspace(rules, "project_entry_after"))

    return "\n".join(lines)


def build_skills(skills, rules):
    lines = []
    lines.append(r"\section*{SKILLS}")
    lines.append(vspace(rules, "section_content"))
    lines.append(r"\begin{itemize}")

    for label, items in skills.items():
        if items:
            values = ", ".join(el(item) for item in items)
            rendered = styled(el(label) + ":", rules, "skills_label") + " " + values
            lines.append(r"  \item " + styled(rendered, rules, "bullets"))

    lines.append(r"\end{itemize}")
    lines.append(vspace(rules, "skills_after"))
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


def check_content_limits(rules, resume, master_resume=None):
    """Reject bullet counts outside the profile limits without changing content."""
    limit = rules["content"]["max_bullets_per_entry"]
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("content.max_bullets_per_entry must be a positive integer")
    minimum = rules["content"].get("min_bullets_per_entry")
    if minimum is not None and (not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1 or minimum > limit):
        raise ValueError("content.min_bullets_per_entry must be a positive integer no greater than max_bullets_per_entry")
    problems = []
    master_projects = {
        entry.get("id"): entry for entry in master_resume.get("projects", [])
    } if master_resume is not None else {}
    master_experience = {
        (entry.get("company"), entry.get("role"), entry.get("dates")): entry
        for entry in master_resume.get("experience", [])
    } if master_resume is not None else {}
    project_ids = [project.get("id") for project in resume.get("projects", [])]
    for project in resume.get("projects", []):
        project_id = project.get("id")
        if not project_id:
            problems.append(f"Project has no stable ID: {project.get('name', '')!r}")
        elif project_ids.count(project_id) > 1:
            problems.append(f"Duplicate project ID {project_id!r}: {project.get('name', '')!r}")
    if master_resume is not None:
        known_ids = {project.get("id") for project in master_resume.get("projects", [])}
        for project in resume.get("projects", []):
            project_id = project.get("id")
            if project_id and project_id not in known_ids:
                problems.append(f"Tailored project ID {project_id!r} is absent from master.yaml: {project.get('name', '')!r}")
    min_projects = rules["content"].get("min_projects")
    max_projects = rules["content"].get("max_projects")
    for key, value in (("min_projects", min_projects), ("max_projects", max_projects)):
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
            raise ValueError(f"content.{key} must be a positive integer")
    if min_projects is not None and max_projects is not None and min_projects > max_projects:
        raise ValueError("content.min_projects cannot exceed content.max_projects")
    projects = resume.get("projects", [])
    if min_projects is not None and len(projects) < min_projects:
        selected = "; ".join(
            f"{project.get('id', 'missing ID')}: {project.get('name', '')}"
            for project in projects
        ) or "none"
        problems.append(
            f"projects: {len(projects)} selected; minimum {min_projects}. "
            f"Selected projects: {selected}"
        )
    if max_projects is not None:
        if len(projects) > max_projects:
            selected = "; ".join(
                f"{project.get('id', 'missing ID')}: {project.get('name', '')}"
                for project in projects
            )
            problems.append(
                f"projects: {len(projects)} selected; maximum {max_projects}. "
                f"Selected projects: {selected}"
            )
    for section, entries in (("experience", resume.get("experience", [])),
                             ("projects", resume.get("projects", []))):
        for entry in entries:
            bullets = entry.get("bullets", [])
            name = entry.get("company") or entry.get("competition") or entry.get("name", "")
            required = minimum
            if minimum is not None and master_resume is not None:
                if section == "projects":
                    source = master_projects.get(entry.get("id"))
                else:
                    source = master_experience.get(
                        (entry.get("company"), entry.get("role"), entry.get("dates"))
                    )
                if source is not None:
                    required = min(minimum, len(source.get("bullets", [])))
            if required is not None and len(bullets) < required:
                selected = "; ".join(
                    f"{bullet.get('id', '')}: {bullet.get('text', '').strip()}"
                    for bullet in bullets
                ) or "none"
                problems.append(
                    f"{section} / {name}: {len(bullets)} bullets; minimum {required} "
                    f"based on the master entry. "
                    f"Selected bullets: {selected}"
                )
            if len(bullets) > limit:
                for bullet in bullets[limit:]:
                    problems.append(
                        f"{section} / {name}: {len(bullets)} bullets; maximum {limit}. "
                        f"Excess bullet {bullet.get('id', '')}: {bullet.get('text', '').strip()!r}"
                    )
    return problems


def render_latex(rules, resume):
    with open(TEMPLATE_FILE, "r") as f:
        template_content = f.read()

    layout = rules["layout"]
    margins = layout["margins"]
    margin_str = ", ".join(side + "=" + margins[side] for side in ["top", "bottom", "left", "right"])
    if (layout["font"], layout["font_package"]) != ("Nimbus Roman No9 L", "mathptmx"):
        raise ValueError("The approved font is Nimbus Roman No9 L via mathptmx")
    if layout["styles"]["section_heading"] != "bold_uppercase_underlined":
        raise ValueError("The approved section heading style is bold_uppercase_underlined")
    if layout["styles"]["name"] != "bold":
        raise ValueError("The approved name style is bold")

    sections = generate_section_order(rules, resume)

    result = template_content
    replacements = {
        "LAYOUT_MARGINS": margin_str,
        "LAYOUT_PAGESIZE": layout["page_size"],
        "LAYOUT_FONT_PACKAGE": layout["font_package"],
        "LAYOUT_FONT_SIZE": layout["font_size"],
        "LAYOUT_NAME_FONT_SIZE": layout["name_font_size"],
        "LAYOUT_NAME_LINE_HEIGHT": layout["name_line_height"],
        "LAYOUT_NAME_STYLE": r"\bfseries",
        "LAYOUT_LINE_SPREAD": str(layout["line_spread"]),
        "LAYOUT_LINK_COLOR": layout["link_color"],
        "LAYOUT_SECTION_STYLE": r"\bfseries\uppercase",
        "LAYOUT_SECTION_RULE": r"[\titlerule]",
        "LAYOUT_PAGE_STYLE": "plain" if layout["page_numbers"] else "empty",
        "LAYOUT_SECTION_BEFORE": spacing(rules, "section_before"),
        "LAYOUT_SECTION_AFTER": spacing(rules, "section_after"),
        "LAYOUT_SECTION_CONTENT": spacing(rules, "section_content"),
        "LAYOUT_HEADER_LINE_GAP": spacing(rules, "header_line_gap"),
        "LAYOUT_AFTER_HEADER": spacing(rules, "after_header"),
        "LAYOUT_SUMMARY_AFTER": spacing(rules, "summary_after"),
        "LAYOUT_PARAGRAPH_SKIP": spacing(rules, "paragraph_skip"),
        "LAYOUT_PARAGRAPH_INDENT": spacing(rules, "paragraph_indent"),
        "LAYOUT_LIST_LEFT_MARGIN": spacing(rules, "list_left_margin"),
        "LAYOUT_LIST_TOP_SEP": spacing(rules, "list_top_sep"),
        "LAYOUT_LIST_PARTOP_SEP": spacing(rules, "list_partop_sep"),
        "LAYOUT_LIST_PARSE_SEP": spacing(rules, "list_parse_sep"),
        "LAYOUT_LIST_ITEM_SEP": spacing(rules, "list_item_sep"),
        "LAYOUT_LIST_BEFORE": spacing(rules, "list_before"),
        "LAYOUT_LIST_AFTER": spacing(rules, "list_after"),
    }
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    result = result.replace("RESUME_NAME", el(resume.get("contact", {}).get("name", "Resume")))
    result = result.replace("RESUME_EMAIL", el(resume.get("contact", {}).get("email", "")))
    result = result.replace("RESUME_PHONE", el(resume.get("contact", {}).get("phone", "")))
    result = result.replace("RESUME_GITHUB_URL", resume.get("contact", {}).get("github", ""))
    result = result.replace("RESUME_LINKEDIN_URL", resume.get("contact", {}).get("linkedin", ""))
    result = result.replace("RESUME_SEEKING", el(resume.get("contact", {}).get("seeking", "")))
    result = result.replace("RESUME_SUMMARY", el(resume.get("summary", "")))
    result = result.replace("SECTION_ORDER", sections)

    if re.search(r"LAYOUT_[A-Z_]+|RESUME_[A-Z_]+|SECTION_ORDER", result):
        raise ValueError("An unresolved LaTeX template placeholder remains")

    return result


def compile_latex(tex_path, compiler_path):
    for pass_number in (1, 2):
        result = subprocess.run(
            [compiler_path, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", str(tex_path)],
            capture_output=True, text=True, cwd=str(tex_path.parent),
        )
        if result.returncode != 0:
            detail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-35:])
            raise RuntimeError(f"pdflatex pass {pass_number} failed for {tex_path}:\n{detail}")


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


def validate(rules, resume, tex_content, output_dir):
    pdf_path = output_dir / "resume.pdf"
    failures, notices = check_rendered_pdf(pdf_path, resume, rules)
    tex_log = output_dir / "resume.log"
    if not tex_log.exists():
        failures.append(f"LaTeX log missing: {tex_log}")
    else:
        box_failures, box_notices = check_overfull(
            tex_log.read_text(), tex_content, rules["layout"]["overfull_tolerance_pt"]
        )
        failures.extend(box_failures)
        notices.extend(box_notices)
    if failures:
        for failure in failures:
            print("  [FAIL] " + failure)
    else:
        min_projects = rules["content"].get("min_projects")
        max_projects = rules["content"].get("max_projects")
        if min_projects is not None and min_projects == max_projects:
            project_limit = f"exactly {min_projects} required"
        elif max_projects is not None:
            project_limit = f"maximum {max_projects}"
        else:
            project_limit = "no project cap"
        print(f"  [PASS] {get_pdf_page_count(pdf_path)} pages; {len(resume.get('projects', []))} projects ({project_limit})")
        print("  [PASS] Rendered line limits, styling, section order, and font")
    for notice in notices:
        print("  [WARN] " + notice)
    print()
    return not failures


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
    parser.add_argument("--profile", choices=("master", "tailored"), default="master",
                        help="Master uses the baseline rules; tailored requires exactly five projects")
    parser.add_argument("--content", type=Path,
                        help="Separate YAML content file (required for the tailored profile)")
    parser.add_argument("--output-dir", type=Path,
                        help="Directory for tailored PDF and LaTeX (default: output/tailored/<content filename>)")
    args = parser.parse_args()

    if args.profile == "master":
        if args.content or args.output_dir:
            parser.error("The master profile uses content/master.yaml and output/; use --profile tailored for separate content and output")
        content_path = MASTER_YAML
        output_dir = OUTPUT_DIR
    else:
        if not args.content:
            parser.error("--profile tailored requires --content with a separate YAML file")
        content_path = args.content.resolve()
        if content_path == MASTER_YAML.resolve():
            parser.error("Tailored content must be a separate file; content/master.yaml is the master source")
        output_dir = (args.output_dir or (OUTPUT_DIR / "tailored" / content_path.stem)).resolve()
        if output_dir == OUTPUT_DIR.resolve():
            parser.error("Tailored output must not overwrite output/resume.pdf")

    print("[1/5] Loading configuration...")
    try:
        rules = load_yaml(RULES_YAML)
        if args.profile == "tailored":
            rules = merge_rules(rules, load_yaml(TAILORED_RULES_YAML))
        resume = load_yaml(content_path)
        master_resume = load_yaml(MASTER_YAML) if args.profile == "tailored" else None
    except Exception as e:
        print("Error loading YAML files: {}".format(e))
        sys.exit(1)

    if args.profile == "tailored" and "section_order" in resume:
        order = resume["section_order"]
        if (not isinstance(order, list) or len(order) != 4
                or any(not isinstance(item, str) for item in order)
                or set(order) != {"experience", "education", "projects", "skills"}
                or order[-1] != "skills"):
            print("[FAIL] Tailored section_order must contain experience, education, and projects once each, followed by skills")
            sys.exit(1)
        rules["layout"]["section_order"] = order[:]

    try:
        content_problems = check_content_limits(rules, resume, master_resume)
    except (KeyError, ValueError) as error:
        print("[FAIL] Content rules: " + str(error))
        sys.exit(1)
    if content_problems:
        for problem in content_problems:
            print("[FAIL] " + problem)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    print("[2/5] Rendering LaTeX template...")
    try:
        tex_content = render_latex(rules, resume)
    except (KeyError, ValueError) as error:
        print("[FAIL] Rendering rules: " + str(error))
        sys.exit(1)

    tex_path = output_dir / "resume.tex"
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
    try:
        compile_latex(tex_path, compiler_path)
    except RuntimeError as error:
        print("[FAIL] " + str(error))
        sys.exit(1)

    pdf_path = output_dir / "resume.pdf"
    if not pdf_path.exists():
        print(f"[FAIL] PDF was not generated. Check {output_dir / 'resume.log'} for errors.")
        sys.exit(1)

    print("[4/5] Validation:")
    try:
        valid = validate(rules, resume, tex_content, output_dir)
    except (RuntimeError, ValueError) as error:
        print("  [FAIL] PDF validation: " + str(error))
        sys.exit(1)
    if not valid:
        sys.exit(1)

    print("[5/5] Done!")
    print("  PDF:    {}".format(pdf_path))
    print("  LaTeX:  {}".format(tex_path))
    print()


if __name__ == "__main__":
    main()
