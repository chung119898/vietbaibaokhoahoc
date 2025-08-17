# app.py
import os
import re
from io import BytesIO
from datetime import datetime
from urllib.parse import urlencode

import requests
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from jinja2 import Template

# ======= UI setup =======
st.set_page_config(page_title="Auto Paper (OpenAlex + Gemini)", layout="wide")
st.title("🧪 Auto Paper: OpenAlex → (tùy chọn) Gemini viết bài")

with st.sidebar:
    st.header("⚙️ Cấu hình tìm kiếm (OpenAlex)")
    topic = st.text_input("Chủ đề", "tăng trưởng xanh và chuyển dịch năng lượng")
    year_range = st.text_input("Khoảng năm (YYYY-YYYY)", "2015-2025")
    per_page = st.number_input("Số mục mỗi trang", 10, 200, 50)
    max_pages = st.number_input("Số trang tối đa", 1, 20, 4)
    max_sources = st.number_input("Giới hạn nguồn đầu ra", 10, 300, 60)
    verify_doi = st.checkbox("Xác thực DOI (HEAD tới doi.org, có thể chậm)", False)
    st.divider()

    st.header("✍️ (Tuỳ chọn) Viết bằng Gemini")
    use_gemini = st.checkbox("Dùng Gemini để soạn bài?", True)
    gemini_model = st.selectbox("Model", ["gemini-1.5-pro", "gemini-1.5-flash"], 0)
    author_name = st.text_input("Tác giả hiển thị", "Nhóm nghiên cứu")
    keywords = st.text_input("Từ khóa", "tăng trưởng xanh; bền vững; năng lượng tái tạo; số hoá")
    subtitle = st.text_input("Phụ đề", "Bài tổng quan hệ thống có trích dẫn học thuật")

    st.divider()
    run = st.button("🚀 Tạo bài viết")

# ======= Helpers =======
def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def year_from_date(s):
    if not s:
        return None
    try:
        return int(str(s)[:4])
    except Exception:
        return None

def doi_url(doi):
    if not doi:
        return None
    doi = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    return f"https://doi.org/{doi}"

def verify_doi_head(doi: str, timeout=8) -> bool:
    if not doi:
        return False
    try:
        r = requests.head(doi_url(doi), allow_redirects=True, timeout=timeout)
        return r.status_code < 400
    except Exception:
        return False

def normalize_author_list(authors):
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

def reconstruct_openalex_abstract(inv):
    """OpenAlex hay trả abstract_inverted_index → ghép lại."""
    if not isinstance(inv, dict) or not inv:
        return ""
    positions = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)

@st.cache_data(show_spinner=False)
def openalex_search(topic, years, per_page=50, max_pages=3):
    base = "https://api.openalex.org/works"
    params = {
        "search": topic,
        "filter": [],
        "per_page": per_page,
        "sort": "relevance_score:desc"
    }
    if years:
        try:
            start, end = years.split("-")
            params["filter"].append(f"from_publication_date:{start}-01-01")
            params["filter"].append(f"to_publication_date:{end}-12-31")
        except ValueError:
            pass
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

def has_valid_url(d):
    for k in ["oa_pdf_url", "url", "landing_page"]:
        if d.get(k):
            return True
    return False

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

def make_sources_bulleted(sources):
    lines = []
    for i, s in enumerate(sources, start=1):
        title = s.get("title") or "(no title)"
        year = s.get("year")
        auths = ", ".join(normalize_author_list(s.get("authors")))
        ven = s.get("venue") or ""
        doi = s.get("doi")
        link = doi_url(doi) if doi else (s.get("url") or s.get("oa_pdf_url") or "")
        lines.append(f"[{i}] {auths} ({year}). {title}. {ven}. {link}".strip())
    return "\n".join(lines)

def enforce_citation_integrity(text, n_sources):
    used = set(int(m.group(1)) for m in re.finditer(r"\[(\d+)\]", text))
    invalid = [i for i in used if i < 1 or i > n_sources]
    fixed = text
    for bad in sorted(invalid, reverse=True):
        fixed = re.sub(rf"\[{bad}\]", "", fixed)
    return fixed

def plot_publications_by_year(df):
    fig = plt.figure()
    counts = df["year"].dropna().astype(int).value_counts().sort_index()
    if counts.empty:
        plt.title("Không đủ dữ liệu năm")
    else:
        counts.plot(kind="bar")
        plt.title("Số bài công bố theo năm")
        plt.xlabel("Năm"); plt.ylabel("Số bài")
        plt.tight_layout()
    return fig

def plot_top_venues(df, topk=10):
    fig = plt.figure()
    vc = df["venue"].dropna().apply(lambda s: s.strip()).value_counts().head(topk)
    if vc.empty:
        plt.title("Không đủ dữ liệu tạp chí")
    else:
        vc.plot(kind="barh")
        plt.title(f"Top {topk} tạp chí/nguồn")
        plt.xlabel("Số bài"); plt.ylabel("Tạp chí/Nguồn")
        plt.tight_layout()
    return fig

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
