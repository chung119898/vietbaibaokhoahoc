#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a journal-style manuscript (Markdown) from a structured YAML file.
- Input: paper.yaml
- Output: paper.md
IMRaD structure + basic PRISMA-style headings for a systematic review.
Requires PyYAML.
"""

import os
import sys
import yaml
from datetime import date
from apa_reference_formatter import format_reference

TEMPLATE_FILE = "TEMPLATE.md"
YAML_FILE = "paper.yaml"
OUTPUT_MD = "paper.md"


def read_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def render_authors(authors):
    lines = []
    for a in authors or []:
        aff = a.get("affiliation", "")
        email = a.get("email", "")
        orcid = a.get("orcid", "")
        extras = []
        if aff:
            extras.append(aff)
        if email:
            extras.append(f"✉ {email}")
        if orcid:
            extras.append(f"ORCID: {orcid}")
        extras_str = " — " + " | ".join(extras) if extras else ""
        lines.append(f"- **{a.get('name','')}**{extras_str}")
    return "\n".join(lines)


def render_keywords(keywords):
    return ", ".join(keywords or [])


def render_ack(ack):
    return (ack or "").strip()


def render_refs(refs):
    out = []
    for r in refs or []:
        out.append(f"- {format_reference(r)}")
    return "\n".join(out)


def fill_template(context):
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        tpl = f.read()

    replacements = {
        "{{TITLE}}": context.get("meta", {}).get("title", ""),
        "{{SUBTITLE}}": context.get("meta", {}).get("subtitle", ""),
        "{{DATE}}": context.get("meta", {}).get("date", str(date.today())),
        "{{AUTHORS}}": render_authors(context.get("meta", {}).get("authors", [])),
        "{{ABSTRACT}}": context.get("abstract", {}).get("text", ""),
        "{{KEYWORDS}}": render_keywords(context.get("abstract", {}).get("keywords", [])),
        "{{INTRO}}": context.get("sections", {}).get("introduction", ""),
        "{{METHODS}}": context.get("sections", {}).get("methods", ""),
        "{{RESULTS}}": context.get("sections", {}).get("results", ""),
        "{{DISCUSSION}}": context.get("sections", {}).get("discussion", ""),
        "{{CONCLUSION}}": context.get("sections", {}).get("conclusion", ""),
        "{{LIMITATIONS}}": context.get("sections", {}).get("limitations", ""),
        "{{ACK}}": render_ack(context.get("acknowledgments", "")),
        "{{DATA_AVAIL}}": context.get("data_availability", ""),
        "{{ETHICS}}": context.get("ethics", ""),
        "{{FUNDING}}": context.get("funding", ""),
        "{{CONFLICTS}}": context.get("conflicts_of_interest", ""),
        "{{PRISMA}}": context.get("sections", {}).get("prisma", ""),
        "{{REFERENCES}}": render_refs(context.get("references", [])),
    }

    for k, v in replacements.items():
        tpl = tpl.replace(k, v)
    return tpl


def main():
    if not os.path.exists(YAML_FILE):
        print(f"[ERROR] Không tìm thấy {YAML_FILE}.")
        sys.exit(1)
    if not os.path.exists(TEMPLATE_FILE):
        print(f"[ERROR] Không tìm thấy {TEMPLATE_FILE}.")
        sys.exit(1)

    ctx = read_yaml(YAML_FILE)

    md = fill_template(ctx)
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"[OK] Đã tạo {OUTPUT_MD}.")


if __name__ == "__main__":
    main()
