#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-generate a PhD-style scholarly article with real citations using Gemini,
sourcing literature from OpenAlex (default) or Google Scholar via SerpAPI.

- Không bịa nguồn: chỉ trích dẫn từ danh sách papers đã xác thực (có DOI/URL).
- Có biểu đồ: publications per year, top venues.
- Có PRISMA flow (Mermaid) dựa trên số lượng thực tế từng bước lọc.
- Bố cục và tông giọng mô phỏng theo bài review hệ thống.

Author: you + ChatGPT
"""

import os
import re
import argparse
import textwrap
from datetime import datetime
from urllib.parse import urlencode

import requests
import pandas as pd
import matplotlib.pyplot as plt
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from jinja2 import Template

# -------- Gemini setup --------
try:
    import google.generativeai as genai
except Exception:
    genai = None


# ==========================
# Utilities
# ==========================
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def year_from_date(s):
    if not s:
        return None
    try:
        return int(str(s)[:4])
    except Exception:
        return None

def clean_text(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip()

def has_valid_url(d):
    for k in ["oa_pdf_url", "url", "landing_page"]:
        if d.get(k):
            return True
    return False

def normalize_author_list(authors):
    # Expect list of dicts with 'name' or simple strings
    if isinstance(authors, list):
        out = []
        for a in authors:
            if isinstance(a, str):
                out.append(a)
            elif isinstance(a, dict):
                name = a.get("name") or (a.get("author") or {}).get("display_name")
                if name:
                    out.append(name)
        return out
    return []

def doi_url(doi):
    if not doi:
        return None
    doi = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    return f"https://doi.org/{doi}"

def verify_doi(doi: str, timeout=8) -> bool:
    if not doi:
        return False
    try:
        r = requests.head(doi_url(doi), allow_redirects=True, timeout=timeout)
        return r.status_code < 400
    except Exception:
        return False

def reconstruct_openalex_abstract(inv):
    """Reconstruct abstract from OpenAlex abstract_inverted_index if available."""
    if not isinstance(inv, dict) or not inv:
        return ""
    positions = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


# ==========================
# Backends: OpenAlex / Scholar via SerpAPI
# ==========================
def openalex_search(topic, years, per_page=50, max_pages=3):
    """
    Search OpenAlex works. Returns list of dicts with keys:
    id, title, authors, year, venue, doi, url, oa_pdf_url, abstract
    """
    print("[OpenAlex] searching…")
    base = "https://api.openalex.org/works"
    params = {
        "search": topic,
        "filter": [],
        "per_page": per_page,
        "sort": "relevance_score:desc"
    }
    # Filters
    if years:
        start, end = years.split("-")
        params["filter"].append(f"from_publication_date:{start}-01-01")
        params["filter"].append(f"to_publication_date:{end}-12-31")
    params["filter"].append("type:journal-article")
    params["filter"] = ",".join(params["filter"])

    out = []
    cursor = "*"
    for _ in range(max_pages):
        q = params.copy()
        q["cursor"] = cursor
        url = f"{base}?{urlencode(q)}"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        for it in data.get("results", []):
            title = clean_text(it.get("title"))
            # OpenAlex uses abstract_inverted_index
            abstract = clean_text(it.get("abstract")) if it.get("abstract") else reconstruct_openalex_abstract(it.get("abstract_inverted_index"))
            doi = it.get("doi")
            primary_location = it.get("primary_location") or {}
            landing = primary_location.get("landing_page_url")
            oa_url = primary_location.get("pdf_url")
            year = year_from_date(it.get("publication_year") or it.get("publication_date"))
            venue = (it.get("host_venue") or {}).get("display_name")
            authors = []
            for au in it.get("authorships", []):
                aname = (au.get("author") or {}).get("display_name")
                if aname:
                    authors.append(aname)
            out.append({
                "id": it.get("id"),
                "title": title,
                "abstract": abstract,
                "doi": doi,
                "url": landing,
                "oa_pdf_url": oa_url,
                "year": year,
                "venue": venue,
                "authors": authors
            })
        meta = data.get("meta", {})
        cursor = meta.get("next_cursor")
        if not cursor:
            break
    return out

def serpapi_scholar_search(topic, num=20):
    """
    Google Scholar via SerpAPI (needs SERPAPI_KEY)
    Returns similar dicts.
    """
    key = os.getenv("SERPAPI_KEY")
    if not key:
        print("[SerpAPI] SERPAPI_KEY missing → skipping Scholar backend.")
        return []
    print("[SerpAPI/Scholar] searching…")
    from serpapi import GoogleSearch
    params = {
        "engine": "google_scholar",
        "q": topic,
        "hl": "en",
        "num": num,
        "api_key": key
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    out = []
    for item in results.get("organic_results", []):
        title = clean_text(item.get("title"))
        year = None
        pub_info = item.get("publication_info", {})
        if isinstance(pub_info, dict):
            year = pub_info.get("year") or pub_info.get("summary")
            if isinstance(year, str):
                m = re.search(r"(19|20)\d{2}", year)
                year = int(m.group()) if m else None
        link = item.get("link")
        snippet = clean_text(item.get("snippet"))
        mdoi = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", (snippet or ""), re.I)
        doi = mdoi.group(0) if mdoi else None
        authors = []
        if isinstance(pub_info.get("authors"), list):
            authors = [clean_text(a.get("name")) for a in pub_info["authors"] if a.get("name")]
        out.append({
            "id": item.get("result_id") or link,
            "title": title,
            "abstract": None,
            "doi": doi,
            "url": link,
            "oa_pdf_url": None,
            "year": year,
            "venue": clean_text(pub_info.get("summary")) if isinstance(pub_info.get("summary"), str) else None,
            "authors": authors
        })
    return out


# ==========================
# Plotting
# ==========================
def plot_publications_by_year(df, outpath):
    counts = df["year"].dropna().astype(int).value_counts().sort_index()
    plt.figure()
    counts.plot(kind="bar")
    plt.title("Số bài công bố theo năm")
    plt.xlabel("Năm")
    plt.ylabel("Số bài")
    plt.tight_layout()
    plt.savefig(outpath, dpi=160)
    plt.close()

def plot_top_venues(df, outpath, topk=10):
    vc = df["venue"].dropna().apply(lambda s: s.strip()).value_counts().head(topk)
    plt.figure()
    vc.plot(kind="barh")
    plt.title(f"Top {topk} tạp chí/nguồn")
    plt.xlabel("Số bài")
    plt.ylabel("Tạp chí/Nguồn")
    plt.tight_layout()
    plt.savefig(outpath, dpi=160)
    plt.close()


# ==========================
# Gemini writing
# ==========================
class GeminiWriter:
    def __init__(self, model_name: str):
        if not genai:
            raise RuntimeError("google-generativeai chưa được cài. Vui lòng `pip install google-generativeai`.")
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Thiếu GEMINI_API_KEY.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=20),
           retry=retry_if_exception_type(Exception))
    def generate(self, prompt: str, max_output_tokens=1800) -> str:
        resp = self.model.generate_content(
            prompt,
            generation_config={"temperature": 0.4, "max_output_tokens": max_output_tokens}
        )
        return resp.text or ""


# ==========================
# Templates & Prompting
# ==========================
MD_TEMPLATE = """---
title: "{{ title }}"
subtitle: "{{ subtitle }}"
author:
  - name: "{{ author }}"
date: "{{ date }}"
lang: vi
---

# {{ title }}

**Tác giả:** {{ author }}

**Từ khóa:** {{ keywords }}

---

## 1. Giới thiệu
{{ intro }}

## 2. Phương pháp (PRISMA / Systematic Review)
{{ methods }}

### 2.1 Sơ đồ PRISMA (mermaid)
```mermaid
{{ prisma_mermaid }}
```

## 3. Kết quả
{{ results }}

### 3.1 Xu hướng công bố theo năm
![Xu hướng công bố](fig_publications_by_year.png)

### 3.2 Top tạp chí/nguồn
![Top tạp chí](fig_top_venues.png)

## 4. Thảo luận
{{ discussion }}

## 5. Kết luận
{{ conclusion }}

### Hạn chế
{{ limitations }}

---

## Tài liệu tham khảo
{% for i, src in enumerate(bibliography, start=1) -%}
[{{i}}] {{ src }}
{% endfor %}
"""

SYSTEM_STYLE_INSTR = """Bạn là một nhà nghiên cứu (tiến sĩ) viết văn phong học thuật, mạch lạc, có trích dẫn theo dạng [#] đúng vị trí. Tuyệt đối không được bịa nguồn hay chèn trích dẫn không có trong danh mục 'CÁC NGUỒN HỢP LỆ'. Nếu không đủ bằng chứng, hãy nói rõ 'chưa đủ bằng chứng từ nguồn hợp lệ' thay vì suy đoán."""

SECTION_PROMPT = """
{system}

CHỦ ĐỀ CHUNG: "{topic}"

CÁC NGUỒN HỢP LỆ (được phép trích dẫn): 
{sources_bulleted}

YÊU CẦU:
- Viết phần: {section_title}
- Ngôn ngữ: tiếng Việt, chuẩn học thuật, rõ ràng.
- Dẫn nguồn tại chỗ theo dạng [#], với # là số thứ tự đúng của danh mục nguồn ở trên (tuyệt đối không trích dẫn ngoài danh mục).
- Không lặp lại tiêu đề.
- Tránh sáo rỗng; tập trung vào bằng chứng, tranh luận chính và “so sánh – đối chiếu”.

ĐỘ DÀI GỢI Ý: {length_hint} từ.

BẮT ĐẦU VIẾT:
"""

def make_sources_bulleted(sources):
    lines = []
    for i, s in enumerate(sources, start=1):
        title = s.get("title") or "(no title)"
        year = s.get("year")
        auths = ", ".join(normalize_author_list(s.get("authors")))
        ven = s.get("venue") or ""
        doi = s.get("doi")
        link = doi_url(doi) if doi else (s.get("url") or s.get("oa_pdf_url") or "")
        bib = f"[{i}] {auths} ({year}). {title}. {ven}. {link}".strip()
        lines.append(bib)
    return "\n".join(lines)

def make_bibliography(sources):
    out = []
    for s in sources:
        auths = normalize_author_list(s.get("authors"))
        auth_str = "; ".join(auths) if auths else "N/A"
        year = s.get("year") or "n.d."
        title = s.get("title") or "Untitled"
        ven = s.get("venue") or ""
        doi = s.get("doi")
        link = doi_url(doi) if doi else (s.get("url") or s.get("oa_pdf_url") or "")
        out.append(f"{auth_str} ({year}). {title}. {ven}. {link}")
    return out

def enforce_citation_integrity(text, n_sources):
    """Xoá mọi trích dẫn không hợp lệ (ví dụ [12] khi chỉ có 10 nguồn)."""
    used = set(int(m.group(1)) for m in re.finditer(r"\[(\d+)\]", text))
    invalid = [i for i in used if i < 1 or i > n_sources]
    fixed = text
    for bad in sorted(invalid, reverse=True):
        fixed = re.sub(rf"\[{bad}\]", "", fixed)
    return fixed


# ==========================
# Main pipeline
# ==========================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True, help="Chủ đề tìm kiếm, ví dụ: 'green growth and energy transition'")
    parser.add_argument("--years", default="2015-2025", help="Khoảng năm, ví dụ 2015-2025")
    parser.add_argument("--max-sources", type=int, default=60)
    parser.add_argument("--backend", choices=["openalex", "scholar"], default="openalex",
                        help="openalex (mặc định), scholar (qua SerpAPI)")
    parser.add_argument("--model", default="gemini-1.5-pro")
    parser.add_argument("--author", default="Nhóm nghiên cứu")
    parser.add_argument("--keywords", default="tăng trưởng xanh; bền vững; năng lượng tái tạo; số hoá")
    parser.add_argument("--subtitle", default="Bài tổng quan hệ thống có trích dẫn học thuật")
    args = parser.parse_args()

    outdir = "output"
    ensure_dir(outdir)

    # 1) Tìm nguồn
    if args.backend == "openalex":
        works = openalex_search(args.topic, args.years, per_page=50, max_pages=4)
    else:
        # FIX: dùng args.max_sources (không phải args.max-sources)
        works = serpapi_scholar_search(args.topic, num=args.max_sources)

    prisma = {"initial": len(works)}

    # 2) Làm sạch + xác thực DOI/URL
    clean = []
    seen_titles = set()
    for w in works:
        title = (w.get("title") or "").strip().lower()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        ok = False
        doi = w.get("doi")
        if doi and verify_doi(doi):
            ok = True
        elif has_valid_url(w):
            ok = True

        if ok:
            y = w.get("year")
            if isinstance(y, str) and y.isdigit():
                y = int(y)
            w["year"] = y
            clean.append(w)

    prisma["deduped"] = len(clean)

    # 3) Sàng lọc theo tiêu đề (chứa từ khoá chủ đề)
    title_keep = []
    topic_tokens = [t.strip().lower() for t in re.split(r"[;,\s]\s*", args.topic) if len(t.strip()) > 2]
    for w in clean:
        t = (w.get("title") or "").lower()
        if any(tok in t for tok in topic_tokens):
            title_keep.append(w)
    if len(title_keep) < max(10, int(0.3*len(clean))):
        title_keep = clean
    prisma["screened_title"] = len(title_keep)

    # 4) Sàng lọc theo abstract (nếu có)
    abs_keep = []
    for w in title_keep:
        ab = (w.get("abstract") or "").lower()
        if ab:
            if any(tok in ab for tok in topic_tokens):
                abs_keep.append(w)
        else:
            abs_keep.append(w)  # không có abstract → giữ lại
    prisma["screened_abstract"] = len(abs_keep)

    # 5) Cắt theo max_sources
    sources = abs_keep[: args.max_sources]
    prisma["included_fulltext"] = len(sources)

    # 6) Lưu CSV nguồn
    df = pd.DataFrame(sources)
    csv_path = os.path.join(outdir, "sources.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"[OK] Saved sources → {csv_path}")

    # 7) Vẽ biểu đồ
    if "year" in df.columns and df["year"].notna().any():
        plot_publications_by_year(df, os.path.join(outdir, "fig_publications_by_year.png"))
    else:
        plt.figure(); plt.title("Không đủ dữ liệu năm"); plt.savefig(os.path.join(outdir, "fig_publications_by_year.png")); plt.close()

    if "venue" in df.columns and df["venue"].notna().any():
        plot_top_venues(df, os.path.join(outdir, "fig_top_venues.png"))
    else:
        plt.figure(); plt.title("Không đủ dữ liệu tạp chí"); plt.savefig(os.path.join(outdir, "fig_top_venues.png")); plt.close()

    # 8) Gom danh mục nguồn hiển thị + bullet cho prompt
    bibliography = make_bibliography(sources)
    sources_bulleted = make_sources_bulleted(sources)

    # 9) Viết từng phần với Gemini
    writer = GeminiWriter(args.model)

    def write_section(title, length_hint=350):
        prompt = SECTION_PROMPT.format(
            system=SYSTEM_STYLE_INSTR,
            topic=args.topic,
            sources_bulleted=sources_bulleted,
            section_title=title,
            length_hint=length_hint
        )
        txt = writer.generate(prompt)
        txt = enforce_citation_integrity(txt, len(bibliography))
        return txt

    intro = write_section("Giới thiệu: bối cảnh, khái niệm trọng tâm, tầm quan trọng và khoảng trống nghiên cứu", 450)
    methods = write_section("Phương pháp: chiến lược tìm kiếm, tiêu chí PRISMA, cơ sở dữ liệu, cách đánh giá chất lượng nghiên cứu", 350)
    results = write_section("Kết quả: các cụm chủ đề, khuynh hướng định lượng, phát hiện chính so với mục tiêu nghiên cứu", 400)
    discussion = write_section("Thảo luận: diễn giải phát hiện, so sánh với tài liệu, hàm ý chính sách/thực hành, tranh luận học thuật", 450)
    conclusion = write_section("Kết luận: tóm tắt đóng góp, hướng nghiên cứu tiếp theo", 220)
    limitations = write_section("Hạn chế: dữ liệu, phương pháp, độ bao phủ; cách khắc phục trong tương lai", 200)

    # 10) PRISMA Mermaid (đầy đủ, đóng chuỗi đúng cách)
    prisma_mermaid = f"""flowchart TB
A[Records identified: {prisma.get('initial', 0)}] --> B[After deduplication: {prisma.get('deduped', 0)}]
B --> C[Title screening included: {prisma.get('screened_title', 0)}]
C --> D[Abstract screening included: {prisma.get('screened_abstract', 0)}]
D --> E[Full-text included: {prisma.get('included_fulltext', 0)}]
"""

    # 11) Render Markdown
    context = {
        "title": f"Tổng quan hệ thống về {args.topic}",
        "subtitle": args.subtitle,
        "author": args.author,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "keywords": args.keywords,
        "intro": intro,
        "methods": methods,
        "results": results,
        "discussion": discussion,
        "conclusion": conclusion,
        "limitations": limitations,
        "prisma_mermaid": prisma_mermaid,
        "bibliography": bibliography
    }
    md = Template(MD_TEMPLATE).render(**context)

    out_md = os.path.join(outdir, "paper.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[OK] Wrote Markdown → {out_md}")
    print("[DONE] Bạn có thể dùng pandoc/typst để xuất PDF nếu muốn.")

if __name__ == "__main__":
    main()
