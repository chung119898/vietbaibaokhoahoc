# app_openalex_streamlit_relaxed.py
import os
import re
from datetime import datetime
from urllib.parse import urlencode

import requests
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from jinja2 import Template

# ================== UI Config ==================
st.set_page_config(page_title="Auto Paper (OpenAlex + Gemini)", layout="wide")
st.title("🧪 Auto Paper: OpenAlex → (tùy chọn) Gemini viết bài")

with st.sidebar:
    st.header("⚙️ Cấu hình tìm kiếm (OpenAlex)")
    topic = st.text_input("Chủ đề", "tăng trưởng xanh và chuyển dịch năng lượng")
    year_range = st.text_input("Khoảng năm (YYYY-YYYY)", "2000-2025")
    per_page = st.number_input("Số mục mỗi trang", 10, 200, 100)
    max_pages = st.number_input("Số trang tối đa", 1, 20, 8)
    max_sources = st.number_input("Giới hạn nguồn đầu ra", 10, 500, 100)
    verify_doi = st.checkbox("Xác thực DOI (HEAD tới doi.org, có thể chậm)", False)
    loosen_types = st.checkbox("Nới lỏng loại tài liệu (journal|proceedings|report|book-chapter)", True)
    auto_expand_vi = st.checkbox("Tự mở rộng từ khoá VI→EN", True)
    show_debug = st.checkbox("Hiển thị URL/meta truy vấn", True)
    st.divider()

    st.header("✍️ (Tuỳ chọn) Viết bằng Gemini")
    use_gemini = st.checkbox("Dùng Gemini để soạn bài?", True)
    gemini_model = st.selectbox("Model", ["gemini-1.5-pro", "gemini-1.5-flash"], 0)
    author_name = st.text_input("Tác giả hiển thị", "Nhóm nghiên cứu")
    keywords = st.text_input("Từ khóa", "tăng trưởng xanh; bền vững; năng lượng tái tạo; số hoá")
    subtitle = st.text_input("Phụ đề", "Bài tổng quan hệ thống có trích dẫn học thuật")

    st.divider()
    run = st.button("🚀 Tạo bài viết")

# ================== Helpers ==================
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
    """OpenAlex có abstract_inverted_index → ghép lại."""
    if not isinstance(inv, dict) or not inv:
        return ""
    positions = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)

def expand_query_vi_to_en(q: str) -> str:
    ql = q.lower()
    extras = []
    # Thêm các mở rộng phổ biến (bạn có thể chỉnh theo lĩnh vực)
    if "tăng trưởng xanh" in ql or "green growth" in ql:
        extras += ["green growth", "green economy", "sustainable growth"]
    if "chuyển dịch năng lượng" in ql or "energy transition" in ql:
        extras += ["energy transition", "decarbonization", "low-carbon transition", "renewable energy transition"]
    if "kinh tế xanh" in ql or "green economy" in ql:
        extras += ["green economy", "circular economy", "sustainable economy"]
    if "phát thải" in ql or "carbon" in ql:
        extras += ["carbon emissions", "emission reduction", "net zero", "carbon neutrality"]
    # Gộp bản gốc + tiếng Anh mở rộng, loại trùng
    parts = [q] + [e for e in extras if e not in q]
    return " ".join(parts)

@st.cache_data(show_spinner=False)
def openalex_search(topic, years, per_page=50, max_pages=3, loosen_types=True, auto_expand_vi=True, show_debug=False):
    base = "https://api.openalex.org/works"
    search_q = expand_query_vi_to_en(topic) if auto_expand_vi else topic
    params = {
        "search": search_q,
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
    types = "journal-article|proceedings-article|report|book-chapter" if loosen_types else "journal-article"
    params["filter"].append(f"type:{types}")
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
        if show_debug:
            st.caption(f"🔎 OpenAlex URL: {url}")
            st.caption(f"📦 meta: {data.get('meta', {})}")
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
        cursor = (data.get("meta") or {}).get("next_cursor")
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

def write_with_gemini(model_name, prompt, max_tokens=1800):
    try:
        import google.generativeai as genai
    except Exception:
        st.error("Chưa cài `google-generativeai`. Chạy: pip install google-generativeai")
        return ""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        st.warning("Thiếu GEMINI_API_KEY → chỉ tạo dữ liệu & biểu đồ, không soạn văn bản.")
        return ""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    resp = model.generate_content(
        prompt,
        generation_config={"temperature": 0.4, "max_output_tokens": max_tokens}
    )
    return resp.text or ""

# ================== Main flow ==================
colL, colR = st.columns([1, 1])

if run:
    with st.spinner("Đang tìm trên OpenAlex..."):
        try:
            works = openalex_search(
                topic, year_range,
                per_page=int(per_page),
                max_pages=int(max_pages),
                loosen_types=loosen_types,
                auto_expand_vi=auto_expand_vi,
                show_debug=show_debug
            )
        except Exception as e:
            st.error(f"Lỗi OpenAlex: {e}")
            works = []

    prisma = {"initial": len(works)}

    # Clean + validate
    clean = []
    seen_titles = set()
    for w in works:
        title_l = (w.get("title") or "").strip().lower()
        if not title_l or title_l in seen_titles:
            continue
        seen_titles.add(title_l)

        ok = False
        doi = w.get("doi")
        if verify_doi and doi and verify_doi_head(doi):
            ok = True
        elif has_valid_url(w) or doi:
            ok = True

        if ok:
            y = w.get("year")
            if isinstance(y, str) and y.isdigit():
                y = int(y)
            w["year"] = y
            clean.append(w)

    prisma["deduped"] = len(clean)

    # Title screening
    topic_tokens = [t.strip().lower() for t in re.split(r"[;,\s]\s*", topic) if len(t.strip()) > 2]
    title_keep = []
    for w in clean:
        t = (w.get("title") or "").lower()
        if any(tok in t for tok in topic_tokens):
            title_keep.append(w)
    if len(title_keep) < max(10, int(0.3*len(clean))):
        title_keep = clean
    prisma["screened_title"] = len(title_keep)

    # Abstract screening
    abs_keep = []
    for w in title_keep:
        ab = (w.get("abstract") or "").lower()
        if ab:
            if any(tok in ab for tok in topic_tokens):
                abs_keep.append(w)
        else:
            abs_keep.append(w)
    prisma["screened_abstract"] = len(abs_keep)

    # Limit sources
    sources = abs_keep[: int(max_sources)]
    prisma["included_fulltext"] = len(sources)

    if sources:
        df = pd.DataFrame(sources)
        st.subheader("📚 Nguồn thu thập được (đã lọc)")
        st.dataframe(df[["title","year","venue","doi","url","oa_pdf_url"]], use_container_width=True, height=350)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Tải sources.csv", csv, "sources.csv", "text/csv")

        with colL:
            st.subheader("📈 Xu hướng công bố theo năm")
            fig1 = plot_publications_by_year(df)
            st.pyplot(fig1, use_container_width=True)

        with colR:
            st.subheader("🏷️ Top tạp chí/nguồn")
            fig2 = plot_top_venues(df, topk=10)
            st.pyplot(fig2, use_container_width=True)

        st.subheader("🧭 PRISMA (Mermaid code)")
        prisma_mermaid = f"""flowchart TB
A[Records identified: {prisma.get('initial', 0)}] --> B[After deduplication: {prisma.get('deduped', 0)}]
B --> C[Title screening included: {prisma.get('screened_title', 0)}]
C --> D[Abstract screening included: {prisma.get('screened_abstract', 0)}]
D --> E[Full-text included: {prisma.get('included_fulltext', 0)}]
"""
        st.code(prisma_mermaid, language="mermaid")

        # Optional: generate paper with Gemini
        paper_md = ""
        if use_gemini:
            sources_bulleted = make_sources_bulleted(sources)
            bibliography = make_bibliography(sources)

            def section(title, length_hint):
                prompt = SECTION_PROMPT.format(
                    system=SYSTEM_STYLE_INSTR,
                    topic=topic,
                    sources_bulleted=sources_bulleted,
                    section_title=title,
                    length_hint=length_hint
                )
                txt = write_with_gemini(gemini_model, prompt)
                return enforce_citation_integrity(txt, len(bibliography))

            with st.spinner("Gemini đang soạn bài..."):
                intro = section("Giới thiệu: bối cảnh, khái niệm trọng tâm, tầm quan trọng và khoảng trống nghiên cứu", 450)
                methods = section("Phương pháp: chiến lược tìm kiếm, tiêu chí PRISMA, cơ sở dữ liệu, cách đánh giá chất lượng nghiên cứu", 350)
                results = section("Kết quả: các cụm chủ đề, khuynh hướng định lượng, phát hiện chính so với mục tiêu nghiên cứu", 400)
                discussion = section("Thảo luận: diễn giải phát hiện, so sánh với tài liệu, hàm ý chính sách/thực hành, tranh luận học thuật", 450)
                conclusion = section("Kết luận: tóm tắt đóng góp, hướng nghiên cứu tiếp theo", 220)
                limitations = section("Hạn chế: dữ liệu, phương pháp, độ bao phủ; cách khắc phục trong tương lai", 200)

                context = {
                    "title": f"Tổng quan hệ thống về {topic}",
                    "subtitle": subtitle,
                    "author": author_name,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "keywords": keywords,
                    "intro": intro,
                    "methods": methods,
                    "results": results,
                    "discussion": discussion,
                    "conclusion": conclusion,
                    "limitations": limitations,
                    "prisma_mermaid": prisma_mermaid,
                    "bibliography": bibliography
                }
                paper_md = Template(MD_TEMPLATE).render(**context)

            st.subheader("📝 Bản thảo (Markdown)")
            st.code(paper_md, language="markdown")
            st.download_button("⬇️ Tải paper.md", paper_md.encode("utf-8"), file_name="paper.md", mime="text/markdown")

        with st.expander("💡 Gợi ý xuất PDF (tuỳ chọn)"):
            st.markdown("""
- Dùng **Pandoc** với filter Mermaid hoặc render Mermaid → PNG trước, rồi nhúng hình vào Markdown.
- Hoặc copy khối Markdown vào Obsidian/MkDocs/VS Code (Markdown Preview Enhanced) để render Mermaid.
""")
    else:
        st.warning("Không thu được nguồn nào. Hãy nới rộng năm, tăng `max_pages`, bật 'Nới lỏng loại tài liệu' và 'Tự mở rộng từ khoá VI→EN', hoặc tắt xác thực DOI.")
else:
    st.info("Nhập cấu hình ở thanh bên và ấn **🚀 Tạo bài viết** để bắt đầu.")
