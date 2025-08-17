# -*- coding: utf-8 -*-
from datetime import datetime

def _fmt_authors(authors):
    if not authors:
        return ""
    parts = []
    for a in authors:
        fam = (a.get("family","") or "").strip()
        giv = (a.get("given","") or "").strip()
        if fam and giv:
            parts.append(f"{fam}, {giv}")
        elif fam:
            parts.append(fam)
        elif giv:
            parts.append(giv)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return " & ".join(parts)
    return ", ".join(parts[:-1]) + ", & " + parts[-1]

def _year(date_str):
    if not date_str:
        return "n.d."
    try:
        return str(datetime.fromisoformat(date_str).year)
    except Exception:
        return date_str

def format_reference(r):
    t = r.get("type","journal_article")
    authors = _fmt_authors(r.get("authors", []))
    year = _year(r.get("date",""))
    title = (r.get("title","") or "").rstrip(".")
    if t == "journal_article":
        journal = r.get("container","")
        vol = r.get("volume","")
        issue = r.get("issue","")
        pages = r.get("pages","")
        doi = r.get("doi","") or r.get("url","")
        segs = [f"{authors} ({year}). {title}. *{journal}*"]
        vol_issue = ""
        if vol and issue:
            vol_issue = f"{vol}({issue})"
        elif vol:
            vol_issue = f"{vol}"
        if vol_issue:
            segs[-1] += f", {vol_issue}"
        if pages:
            segs[-1] += f", {pages}"
        segs[-1] += "."
        if doi:
            segs.append(f"https://doi.org/{doi}" if doi and "http" not in doi and "/" in doi else doi)
        return " ".join(segs)
    elif t == "book":
        publisher = r.get("publisher","")
        return f"{authors} ({year}). *{title}*. {publisher}."
    elif t == "conference_paper":
        conf = r.get("container","")
        pages = r.get("pages","")
        url = r.get("url","")
        base = f"{authors} ({year}). {title}. In *{conf}*"
        if pages:
            base += f", {pages}."
        else:
            base += "."
        if url:
            base += f" {url}"
        return base
    elif t == "web_article":
        site = r.get("container","")
        url = r.get("url","")
        return f"{authors} ({year}). {title}. *{site}*. {url}"
    else:
        return f"{authors} ({year}). {title}."
