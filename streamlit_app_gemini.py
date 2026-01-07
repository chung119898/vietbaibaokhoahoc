# streamlit_app_gemini.py (LaTeX Version)
import os
import re
from datetime import datetime
from urllib.parse import urlencode

import requests
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from jinja2 import Template
# import pdfkit # Không cần pdfkit nữa vì ta xuất ra .tex

# ================== UI Config ==================
st.set_page_config(page_title="Auto Paper (OpenAlex + Gemini -> LaTeX)", layout="wide")
st.title("🧪 Auto Paper: OpenAlex → Gemini → LaTeX (.tex)")

with st.sidebar:
    st.header("⚙️ Cấu hình tìm kiếm (OpenAlex)")
    topic = st.text_input("Chủ đề (VD: Ứng dụng AI trong y tế)", "Ứng dụng AI trong chẩn đoán hình ảnh")
    year_range = st.text_input("Khoảng năm (YYYY-YYYY)", "2018-2025")
    per_page = st.number_input("Số mục tìm kiếm mỗi trang", 10, 200, 50)
    max_pages = st.number_input("Số trang tối đa", 1, 20, 2)
    max_sources = st.number_input("Giới hạn nguồn đầu ra", 5, 100, 20)
    auto_expand_vi = st.checkbox("Tự mở rộng từ khoá VI→EN", True)

    st.subheader("🔐 Gemini API key")
    gemini_key_manual = st.text_input("GEMINI_API_KEY", type="password")
    if gemini_key_manual:
        os.environ["GEMINI_API_KEY"] = gemini_key_manual

    st.divider()
    st.header("✍️ Cấu hình bài báo")
    use_gemini = st.checkbox("Dùng Gemini viết nội dung?", True)
    gemini_model = st.selectbox("Model", ["gemini-1.5-flash", "gemini-1.5-pro"], 0)
    paper_language = st.selectbox("Ngôn ngữ bài viết", ["Tiếng Việt", "English"], 0)
    author_name = st.text_input("Tác giả", "Nguyen Van A")
    affiliation = st.text_input("Đơn vị công tác", "Đại học Bách Khoa Hà Nội")
    
    st.divider()
    run = st.button("🚀 Tạo bài báo LaTeX")

# ================== Helpers ==================
def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def year_from_date(s):
    if not s: return None
    try: return int(str(s)[:4])
    except: return None

def doi_url(doi):
    if not doi: return None
    doi = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    return f"https://doi.org/{doi}"

def normalize_author_list(authors):
    if isinstance(authors, list):
        out = []
        for a in authors:
            if isinstance(a, str): out.append(a)
            elif isinstance(a, dict):
                name = a.get("name") or (a.get("author") or {}).get("display_name")
                if name: out.append(name)
        return out
    return []

def expand_query_vi_to_en(q: str) -> str:
    # Hàm đơn giản mở rộng từ khóa tiếng Việt sang tiếng Anh để tìm trên OpenAlex tốt hơn
    ql = q.lower()
    extras = []
    if "ai" in ql or "trí tuệ nhân tạo" in ql: extras += ["artificial intelligence", "deep learning", "machine learning"]
    if "y tế" in ql or "chẩn đoán" in ql: extras += ["medical imaging", "healthcare", "diagnosis"]
    if "việt nam" in ql: extras += ["Vietnam", "developing countries"]
    parts = [q] + [e for e in extras if e not in q]
    return " ".join(parts)

@st.cache_data(show_spinner=False)
def openalex_search(topic, years, per_page=50, max_pages=2, auto_expand_vi=True):
    base = "https://api.openalex.org/works"
    search_q = expand_query_vi_to_en(topic) if auto_expand_vi else topic
    params = {
        "search": search_q,
        "filter": ["type:journal-article|proceedings-article"], # Chỉ lấy bài báo tạp chí/hội nghị
        "per_page": per_page,
        "sort": "relevance_score:desc"
    }
    if years:
        try:
            start, end = years.split("-")
            params["filter"].append(f"from_publication_date:{start}-01-01")
            params["filter"].append(f"to_publication_date:{end}-12-31")
        except: pass
    
    params["filter"] = ",".join(params["filter"])
    
    out = []
    cursor = "*"
    for _ in range(max_pages):
        q = params.copy()
        q["cursor"] = cursor
        try:
            r = requests.get(base, params=q, timeout=30)
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])
            for it in results:
                # Lấy thông tin cơ bản
                title = clean_text(it.get("title"))
                abstract = ""
                # Xử lý abstract inverted index của OpenAlex
                inv = it.get("abstract_inverted_index")
                if inv:
                    positions = []
                    for word, idxs in inv.items():
                        for i in idxs: positions.append((i, word))
                    positions.sort()
                    abstract = " ".join(w for _, w in positions)
                
                doi = it.get("doi")
                year = year_from_date(it.get("publication_year"))
                venue = (it.get("host_venue") or {}).get("display_name")
                authors = []
                for au in it.get("authorships", []):
                    aname = (au.get("author") or {}).get("display_name")
                    if aname: authors.append(aname)
                
                if title and year:
                    out.append({
                        "id": it.get("id"),
                        "title": title,
                        "abstract": abstract,
                        "doi": doi,
                        "year": year,
                        "venue": venue,
                        "authors": authors,
                        "cited_by_count": it.get("cited_by_count", 0)
                    })
            cursor = (data.get("meta") or {}).get("next_cursor")
            if not cursor: break
        except Exception as e:
            st.error(f"Lỗi kết nối OpenAlex: {e}")
            break
    return out

# --- Tạo BibTeX và danh sách nguồn ---
def generate_bibtex_key(source, index):
    # Tạo key dạng: AuthorYear (vd: Nguyen2023)
    if source.get("authors"):
        last_name = source["authors"][0].split()[-1]
        last_name = re.sub(r"[^a-zA-Z]", "", last_name) # Chỉ giữ chữ cái
    else:
        last_name = "Unknown"
    return f"{last_name}{source.get('year') or 'nd'}_{index}"

def make_bibtex_entries(sources):
    # Tạo nội dung cho môi trường thebibliography hoặc file .bib
    entries = []
    keys = []
    for i, s in enumerate(sources, 1):
        key = generate_bibtex_key(s, i)
        keys.append(key)
        
        # Định dạng đơn giản cho \bibitem
        authors = " and ".join(s.get("authors", []))
        title = s.get("title", "")
        venue = s.get("venue", "")
        year = s.get("year", "")
        doi = s.get("doi", "").replace("https://doi.org/", "")
        
        # Tạo entry dạng \bibitem{key} Author, Title, Venue, Year.
        entry = f"\\bibitem{{{key}}} {authors}. ``{title}''. \\textit{{{venue}}}, {year}. DOI: {doi}."
        entries.append(entry)
    return entries, keys

def make_sources_bulleted(sources, keys):
    lines = []
    for i, s in enumerate(sources):
        title = s.get("title")
        year = s.get("year")
        key = keys[i] # Key BibTeX tương ứng
        lines.append(f"[{i+1}] (Cite Key: {key}) {title} ({year})")
    return "\n".join(lines)

# --- Xử lý đồ thị ---
def plot_publications_by_year(df):
    fig = plt.figure(figsize=(6, 4))
    counts = df["year"].dropna().astype(int).value_counts().sort_index()
    if not counts.empty:
        counts.plot(kind="bar", color="teal")
        plt.title("Publications per Year")
        plt.xlabel("Year")
        plt.ylabel("Count")
        plt.tight_layout()
    return fig

# --- Gemini setup ---
def write_with_gemini(model_name, prompt):
    try:
        import google.generativeai as genai
    except:
        return "Error: Missing google-generativeai lib."
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key: return "Error: Missing API Key."
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    try:
        resp = model.generate_content(prompt)
        return resp.text
    except Exception as e:
        return f"% Error generating content: {e}"

# --- LATEX TEMPLATE ---
LATEX_TEMPLATE = r"""
\documentclass[12pt, a4paper]{article}
\usepackage[utf8]{inputenc}
{% if lang == 'vi' %}
\usepackage[utf8]{vietnam} % Gói hỗ trợ tiếng Việt
{% endif %}
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{geometry}
\geometry{left=2.5cm, right=2.5cm, top=2.5cm, bottom=2.5cm}

\title{\textbf{ {{ title }} }}
\author{ {{ author }} \\ \small {{ affiliation }} }
\date{\today}

\begin{document}

\maketitle

\begin{abstract}
{{ abstract_content }}
\end{abstract}

\section{ {{ intro_title }} }
{{ intro_content }}

\section{ {{ methods_title }} }
{{ methods_content }}

\section{ {{ results_title }} }
{{ results_content }}

\begin{figure}[h!]
    \centering
    \includegraphics[width=0.8\textwidth]{fig_publications_by_year.png}
    \caption{Trend of publications over the years.}
    \label{fig:trend}
\end{figure}

\section{ {{ discussion_title }} }
{{ discussion_content }}

\section{ {{ conclusion_title }} }
{{ conclusion_content }}

% Tự động chèn tài liệu tham khảo
\begin{thebibliography}{99}
{% for item in bib_entries %}
{{ item }}
{% endfor %}
\end{thebibliography}

\end{document}
"""

# ================== Main Flow ==================
colL, colR = st.columns([1, 1])

if run:
    # 1. Tìm kiếm OpenAlex
    with st.spinner("Đang tìm dữ liệu từ OpenAlex..."):
        works = openalex_search(topic, year_range, per_page, max_pages, auto_expand_vi)
    
    if not works:
        st.error("Không tìm thấy bài báo nào. Thử thay đổi từ khóa hoặc năm.")
    else:
        # Lọc sơ bộ: Lấy top N bài có trích dẫn cao nhất hoặc mới nhất
        works.sort(key=lambda x: x.get('cited_by_count', 0), reverse=True)
        sources = works[:int(max_sources)]
        
        df = pd.DataFrame(sources)
        
        # 2. Tạo BibTeX keys và entries
        bib_entries, bib_keys = make_bibtex_entries(sources)
        sources_list_str = make_sources_bulleted(sources, bib_keys)

        # 3. Vẽ biểu đồ và lưu file ảnh (để LaTeX dùng)
        fig = plot_publications_by_year(df)
        fig.savefig("fig_publications_by_year.png", dpi=300)
        
        with colL:
            st.subheader("📚 Nguồn dữ liệu (Top cited)")
            st.dataframe(df[["year", "title", "venue", "cited_by_count"]], height=300)
            st.pyplot(fig)

        # 4. Viết bài bằng Gemini
        if use_gemini:
            st.subheader("🤖 Gemini đang viết bài (LaTeX)...")
            
            # Cấu hình ngôn ngữ cho prompt
            if paper_language == "Tiếng Việt":
                lang_code = "vi"
                section_titles = {
                    "intro": "Giới thiệu", "methods": "Phương pháp nghiên cứu",
                    "results": "Kết quả", "discussion": "Thảo luận", "conclusion": "Kết luận"
                }
                system_prompt = f"""
                Bạn là một nhà nghiên cứu khoa học viết bài bằng tiếng Việt chuẩn mực. 
                Nhiệm vụ: Viết một phần của bài báo khoa học về chủ đề: "{topic}".
                Yêu cầu quan trọng:
                1. Đầu ra phải là văn bản thô (plain text) hoặc mã LaTeX cơ bản (ví dụ: \textit{{...}}, \textbf{{...}}).
                2. SỬ DỤNG TRÍCH DẪN: Bạn phải trích dẫn các nguồn sau đây bằng lệnh \cite{{KEY}}.
                Danh sách nguồn hợp lệ (Kèm Key để trích dẫn):
                {sources_list_str}
                3. Tuyệt đối không bịa đặt nguồn. Chỉ dùng \cite{{KEY}} với các KEY có trong danh sách trên.
                4. Không dùng Markdown (như **bold**), hãy dùng LaTeX (như \\textbf{{bold}}).
                """
            else:
                lang_code = "en"
                section_titles = {
                    "intro": "Introduction", "methods": "Methodology",
                    "results": "Results", "discussion": "Discussion", "conclusion": "Conclusion"
                }
                system_prompt = f"""
                You are a scientific researcher writing in academic English.
                Task: Write a section for a paper on the topic: "{topic}".
                Key Requirements:
                1. Output plain text or basic LaTeX code (e.g., \textit{{...}}).
                2. CITATIONS: You MUST cite the provided sources using \cite{{KEY}}.
                Valid Sources List (with Keys):
                {sources_list_str}
                3. Do not fabricate citations. Only use \cite{{KEY}} from the list above.
                4. Do not use Markdown, use LaTeX syntax.
                """

            # Hàm gọi Gemini cho từng phần
            def generate_section(sec_name, context_note=""):
                prompt = f"{system_prompt}\n\nVIẾT PHẦN: {sec_name.upper()}.\n{context_note}\nĐộ dài khoảng 300-400 từ."
                with st.spinner(f"Đang viết phần {sec_name}..."):
                    return write_with_gemini(gemini_model, prompt)

            # Generate từng phần
            abstract_content = generate_section("Abstract (Tóm tắt)", "Tóm tắt mục tiêu, phương pháp và kết quả chính.")
            intro_content = generate_section("Introduction", "Nêu bối cảnh, lý do nghiên cứu.")
            methods_content = generate_section("Methods", "Mô tả cách thức tổng hợp tài liệu từ OpenAlex.")
            results_content = generate_section("Results", "Tổng hợp các phát hiện chính từ các nguồn tài liệu.")
            discussion_content = generate_section("Discussion", "Bàn luận về ý nghĩa, so sánh các nghiên cứu.")
            conclusion_content = generate_section("Conclusion", "Kết luận ngắn gọn.")

            # 5. Render Template
            ctx = {
                "lang": lang_code,
                "title": f"Báo cáo tổng quan về {topic}" if lang_code == 'vi' else f"Review on {topic}",
                "author": author_name,
                "affiliation": affiliation,
                "abstract_content": abstract_content,
                "intro_title": section_titles["intro"],
                "intro_content": intro_content,
                "methods_title": section_titles["methods"],
                "methods_content": methods_content,
                "results_title": section_titles["results"],
                "results_content": results_content,
                "discussion_title": section_titles["discussion"],
                "discussion_content": discussion_content,
                "conclusion_title": section_titles["conclusion"],
                "conclusion_content": conclusion_content,
                "bib_entries": bib_entries
            }

            latex_source = Template(LATEX_TEMPLATE).render(**ctx)
            
            with colR:
                st.success("Đã tạo xong mã LaTeX!")
                st.text_area("LaTeX Source", latex_source, height=600)
                
                # Nút tải xuống
                st.download_button(
                    label="⬇️ Tải file paper.tex",
                    data=latex_source,
                    file_name="paper.tex",
                    mime="application/x-tex"
                )
                
                st.warning("Lưu ý: Để biên dịch (compile) file này, hãy tải cả hình ảnh biểu đồ bên dưới và để cùng thư mục.")
                with open("fig_publications_by_year.png", "rb") as f:
                    st.download_button(
                        label="⬇️ Tải biểu đồ (png)",
                        data=f,
                        file_name="fig_publications_by_year.png",
                        mime="image/png"
                    )
