"""Check rendered resume layout against config/rules.yaml.

Poppler's XML output exposes physical text lines and embedded font faces. This
lets the build check line limits and styling in the PDF, rather than guessing
from YAML character counts.
"""

from dataclasses import dataclass
import re
import subprocess
import xml.etree.ElementTree as ET


SECTION_NAMES = {
    "experience": "WORK EXPERIENCE",
    "education": "EDUCATION",
    "projects": "ACADEMIC PROJECTS / COMPETITION PROJECT / RESEARCH EXPERIENCE",
    "skills": "SKILLS",
}


@dataclass
class Span:
    text: str
    left: float
    family: str
    size: float
    color: str

    @property
    def style(self):
        if "Ital" in self.family:
            return "italic"
        if "Medi" in self.family or "Bold" in self.family:
            return "bold"
        return "regular"


@dataclass
class Line:
    page: int
    top: float
    left: float
    spans: list[Span]

    @property
    def text(self):
        return "".join(span.text for span in self.spans).strip()


def read_pdf_lines(pdf_path):
    result = subprocess.run(
        ["pdftohtml", "-xml", "-stdout", str(pdf_path)],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError(f"pdftohtml failed: {result.stderr.strip()}")
    root = ET.fromstring(result.stdout)
    lines = []
    page_widths = []
    fonts = {
        font.attrib["id"]: font.attrib
        for font in root.iter("fontspec")
    }
    for page in root.findall("page"):
        number = int(page.attrib["number"])
        page_widths.append(float(page.attrib["width"]))
        fragments = []
        for element in page.findall("text"):
            font = fonts[element.attrib["font"]]
            fragments.append((
                float(element.attrib["top"]),
                Span(
                    text="".join(element.itertext()),
                    left=float(element.attrib["left"]),
                    family=font["family"],
                    size=float(font["size"]),
                    color=font["color"],
                ),
            ))
        fragments.sort(key=lambda pair: (pair[0], pair[1].left))
        page_lines = []
        for top, span in fragments:
            if page_lines and abs(top - page_lines[-1].top) <= 2:
                page_lines[-1].spans.append(span)
                page_lines[-1].left = min(page_lines[-1].left, span.left)
            else:
                page_lines.append(Line(number, top, span.left, [span]))
        for line in page_lines:
            line.spans.sort(key=lambda span: span.left)
        lines.extend(page_lines)
    return lines, page_widths


def bullet_manifest(resume, rules):
    """List every bullet in rendered order, including education bullets."""
    bullets = []
    for section in rules["layout"]["section_order"]:
        if section == "experience":
            for entry in resume.get("experience", []):
                for bullet in entry.get("bullets", []):
                    bullets.append((section, entry.get("company", ""), bullet.get("id", ""), bullet["text"].strip()))
        elif section == "education":
            for entry in resume.get("education", []):
                name = entry.get("institution", "")
                bullets.append((section, name, "degree", entry["degree"]))
                if entry.get("specialisation"):
                    bullets.append((section, name, "specialisation", entry["specialisation"]))
                if entry.get("honours") or entry.get("gpa"):
                    bullets.append((section, name, "honours", " ".join(
                        entry[key] for key in ("honours", "gpa") if entry.get(key)
                    )))
                if entry.get("modules"):
                    bullets.append((section, name, "modules", " ".join(entry["modules"])))
            for cert in resume.get("certifications", []):
                bullets.append((section, "Virtual Training", "certification", cert["title"]))
        elif section == "projects":
            for entry in resume.get("projects", []):
                for bullet in entry.get("bullets", []):
                    bullets.append((section, entry.get("competition", ""), bullet.get("id", ""), bullet["text"].strip()))
        elif section == "skills":
            for label, items in resume.get("skills", {}).items():
                if items:
                    bullets.append((section, label, label, label + ": " + ", ".join(items)))
    return bullets


def find_line(lines, prefix, start=0):
    for index in range(start, len(lines)):
        if lines[index].text.startswith(prefix):
            return index
    return None


def rendered_bullets(lines):
    """Return (start line, number of physical lines) for every visible bullet."""
    result = []
    for index, line in enumerate(lines):
        if not line.text.startswith("•"):
            continue
        count = 1
        next_index = index + 1
        while next_index < len(lines):
            following = lines[next_index]
            if following.text.startswith("•") or following.left <= line.left + 5:
                break
            count += 1
            next_index += 1
        result.append((index, count))
    return result


def check_style(failures, lines, text, expected, description):
    matches = [span for line in lines for span in line.spans if text in span.text]
    if not matches:
        failures.append(f"{description}: text missing from PDF: {text!r}")
    elif not any(span.style == expected for span in matches):
        failures.append(f"{description}: expected {expected} text: {text!r}")


def check_rendered_pdf(pdf_path, resume, rules):
    """Return (failures, notices) with exact entry text for layout problems."""
    layout = rules["layout"]
    lines, page_widths = read_pdf_lines(pdf_path)
    failures = []
    notices = []
    if not lines:
        return ["PDF has no extractable text"], notices

    # PDF physical page, font, and color checks.
    page_count = len(page_widths)
    if page_count > layout["page_limit"]:
        failures.append(f"Page limit: PDF has {page_count} pages; maximum is {layout['page_limit']}")
    expected_width = {"letterpaper": 918, "a4paper": 893}.get(layout["page_size"])
    if expected_width is None or any(abs(width - expected_width) > 2 for width in page_widths):
        failures.append(f"Page size: expected {layout['page_size']}; PDF widths are {page_widths}")
    body_size = float(layout["font_size"].removesuffix("pt")) * 1.5
    name_size = float(layout["name_font_size"].removesuffix("pt")) * 1.5
    for line in lines:
        for span in line.spans:
            if "NimbusRomNo9L" not in span.family:
                failures.append(f"Font: unexpected face {span.family!r} on page {line.page}: {span.text!r}")
            expected_size = name_size if resume["contact"]["name"] in span.text else body_size
            if abs(span.size - expected_size) > 1:
                failures.append(f"Font size: expected {expected_size/1.5:g}pt on page {line.page}: {span.text!r}")
            if span.color.lower() != "#000000":
                failures.append(f"Text color: expected black on page {line.page}: {span.text!r}")

    # Header, summary, and section order.
    summary_at = find_line(lines, "PROFESSIONAL SUMMARY")
    first_section_at = find_line(lines, SECTION_NAMES[layout["section_order"][0]])
    if summary_at is None or first_section_at is None:
        failures.append("Could not locate the summary and first section in the PDF")
    else:
        header_count = summary_at
        summary_count = first_section_at - summary_at - 1
        if header_count != layout["header_lines"]:
            failures.append(f"Header: {header_count} rendered lines; expected {layout['header_lines']}")
        if summary_count > layout["max_summary_lines"]:
            failures.append(f"Summary: {summary_count} rendered lines; maximum {layout['max_summary_lines']}. Text: {resume['summary'].strip()!r}")
        for line in lines[summary_at + 1:first_section_at]:
            if any(span.style != "regular" for span in line.spans):
                failures.append(f"Summary must use regular text: {line.text!r}")
    positions = [find_line(lines, SECTION_NAMES[key]) for key in layout["section_order"]]
    if None in positions or positions != sorted(positions):
        failures.append(f"Section order: expected {layout['section_order']}; found positions {positions}")

    # The PDF itself must contain the requested bold and italic font faces.
    check_style(failures, lines, resume["contact"]["name"], "bold", "Name")
    for heading in ["PROFESSIONAL SUMMARY", *[SECTION_NAMES[key] for key in layout["section_order"]]]:
        check_style(failures, lines, heading, "bold", "Section heading")
    for entry in resume.get("experience", []):
        check_style(failures, lines, entry["company"] + ", " + entry["role"], "bold", "Work heading")
        if entry.get("tech"):
            check_style(failures, lines, entry["tech"], "regular", "Work technologies")
        check_style(failures, lines, entry["dates"], "regular", "Work dates")
    for entry in resume.get("education", []):
        name = entry["institution"].split(" (")[0]
        check_style(failures, lines, name, "bold", "Institution")
        check_style(failures, lines, entry["dates"], "regular", "Education dates")
        for module in entry.get("modules", []):
            parsed = re.match(r"^\(\d+\)\s*(.*?)(?:\s*\[.*\])?$", module)
            if parsed:
                check_style(failures, lines, parsed.group(1), "italic", "Module title")
    for cert in resume.get("certifications", []):
        if ": " in cert["title"]:
            check_style(failures, lines, cert["title"].split(": ", 1)[1], "italic", "Certification name")
    for entry in resume.get("projects", []):
        check_style(failures, lines, entry["competition"], "bold", "Project heading")
        if entry.get("tech"):
            check_style(failures, lines, entry["tech"], "regular", "Project technologies")
        check_style(failures, lines, entry["dates"], "regular", "Project dates")
    for label in resume.get("skills", {}):
        check_style(failures, lines, label + ":", "bold", "Skills label")

    # Match each rendered bullet to its exact YAML text and count PDF lines.
    expected_bullets = bullet_manifest(resume, rules)
    actual_bullets = rendered_bullets(lines)
    if len(actual_bullets) != len(expected_bullets):
        failures.append(
            f"Bullet extraction: found {len(actual_bullets)} bullets in PDF; expected {len(expected_bullets)} from YAML"
        )
    else:
        for (section, entry, bullet_id, text), (_, physical_lines) in zip(expected_bullets, actual_bullets):
            if section in {"experience", "projects", "skills"} and physical_lines > layout["max_bullet_lines"]:
                failures.append(
                    f"{section} / {entry} / {bullet_id}: {physical_lines} rendered bullet lines; "
                    f"maximum {layout['max_bullet_lines']}. Exact text: {text!r}"
                )
        for (section, entry, bullet_id, text), (start_index, _) in zip(expected_bullets, actual_bullets):
            first_line = lines[start_index]
            if section in {"experience", "projects"} and any(span.style != "regular" for span in first_line.spans):
                failures.append(f"{section} / {entry} / {bullet_id}: bullet must be regular text. Exact text: {text!r}")
            if section == "skills" and not any(span.style == "regular" for span in first_line.spans):
                failures.append(f"skills / {entry}: skill values must be regular text. Exact text: {text!r}")

    # A project heading, its title, and its first bullet must begin together.
    search_from = 0
    for entry in resume.get("projects", []):
        heading = entry["competition"]
        label = entry.get("project_label", "Project") + ":"
        heading_at = find_line(lines, heading, search_from)
        title_at = find_line(lines, label, (heading_at + 1) if heading_at is not None else search_from)
        if heading_at is None or title_at is None:
            failures.append(f"Project introduction missing: {heading!r} / {label} {entry['name']!r}")
            continue
        search_from = title_at + 1
        heading_count = title_at - heading_at
        first_bullet = next((index for index, _ in actual_bullets if index > title_at), None)
        if first_bullet is None:
            failures.append(f"Project has no rendered first bullet: {heading!r}")
            continue
        title_count = first_bullet - title_at
        if heading_count > layout["max_project_heading_lines"]:
            failures.append(f"Project heading: {heading_count} lines; maximum {layout['max_project_heading_lines']}. Text: {heading!r}")
        if title_count > layout["max_project_title_lines"]:
            failures.append(f"Project title: {title_count} lines; maximum {layout['max_project_title_lines']}. Text: {label} {entry['name']!r}")
        if len({lines[i].page for i in (heading_at, title_at, first_bullet)}) != 1:
            failures.append(f"Project introduction crosses pages: {heading!r} / {label} {entry['name']!r}")
        if any(span.style != "italic" for span in lines[title_at].spans):
            failures.append(f"Project title is not fully italic: {label} {entry['name']!r}")

    return failures, notices


def check_overfull(log_text, tex_content, tolerance_pt):
    failures = []
    notices = []
    tex_lines = tex_content.splitlines()
    pattern = r"Overfull \\(hbox|vbox) \((\d+(?:\.\d+)?)pt too (?:wide|high)\)(?: in paragraph)?(?: at lines? (\d+)(?:--(\d+))?)?"
    for match in re.finditer(pattern, log_text):
        kind, amount, first, last = match.groups()
        width = float(amount)
        if first and 0 < int(first) <= len(tex_lines):
            source = tex_lines[int(first)-1].strip()
            source = re.sub(r"^.*?\\item\s*", "", source)
            source = source.replace(r"\$", "$").replace(r"\%", "%").replace(r"\&", "&")
            source = source.replace(r"\textasciitilde{}", "~")
            source = re.sub(r"\\textnormal\{|\}$", "", source)
            location = f"LaTeX line {first}"
            message = f"Overfull {kind} by {amount}pt at {location} (limit {tolerance_pt:g}pt). Exact text: {source!r}"
        else:
            message = f"Overfull {kind} by {amount}pt (limit {tolerance_pt:g}pt). LaTeX log has no source line."
        (failures if width > tolerance_pt else notices).append(message)
    return failures, notices
