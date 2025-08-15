import streamlit as st
import requests
import json
import re
import random
import numpy as np
import urllib.parse
import tempfile
import subprocess
import os

st.set_page_config(page_title="Auto Research Writer (Gemini API, LaTeX PDF)", page_icon="🧠", layout="wide")

ARTICLE_TYPES = {
    "Systematic Review": [
        "Abstract",
        "1. Introduction",
        "2. Methods (Search & Selection)",
        "3. Results (Bibliometrics/Findings)",
        "4. Thematic Synthesis",
        "5. Gaps & Future Directions",
        "6. Conclusion",
    ],
    "Empirical Study": [
        "Abstract",
        "1. Introduction",
        "2. Literature Review",
        "3. Data & Methods",
        "4. Results",
        "5. Robustness & Limitations",
        "6. Conclusion",
    ],
    "Policy Brief": [
        "Executive Summary",
        "1. Background",
        "2. Problem Statement",
        "3. Policy Options",
        "4. Recommendations",
        "5. Implementation & Monitoring",
        "6. Conclusion",
    ],
}

DEFAULT_PROMPT_INSTRUCTIONS = (
    "You are an expert academic writer. Write clear, cohesive, and citation-aware prose suitable for a peer-reviewed venue. "
    "Avoid hallucinated statistics. If asserting facts, hedge appropriately or request verification. Use concise paragraphs."
)

def compose_prompt_latex(topic: str, article_type: str, outline: list, extra_instructions: str, want_refs: bool):
    outline_block = "\n".join(f"\\section*{{{sec}}}" for sec in outline)
    refs_guidance = (
        "At the end, include a section 'References' with plausible APA-style citations (author, year, title, venue). "
        "Do NOT include URLs or DOIs. Only output author, year, title, venue."
    ) if want_refs else ""
    return f"""
{DEFAULT_PROMPT_INSTRUCTIONS}
{extra_instructions}

Write a {article_type} on the topic: "{topic}".
Write each section as fully and comprehensively as possible, with no word limit. Do not summarize or shorten any part.
Use the following LaTeX structure exactly and write content under each section header:
{outline_block}

Tone: scholarly but accessible. Avoid filler. Where evidence is uncertain, say so explicitly.
{refs_guidance}

Return a complete LaTeX article, starting with \\documentclass, including \\title, \\author, \\date, \\maketitle, and ending with \\end{{document}}.
""".strip()

def generate_with_gemini_api(api_key: str, prompt: str, model_name: str = "gemini-2.0-flash"):
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key
    }
    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }
    response = requests.post(endpoint, headers=headers, data=json.dumps(data))
    if response.status_code != 200:
        raise RuntimeError(f"Gemini API error: {response.status_code} {response.text}")
    result = response.json()
    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise RuntimeError(f"Gemini API response parsing error: {result}")

def scholar_search_url(ref):
    q = urllib.parse.quote(ref)
    return f"https://scholar.google.com/scholar?q={q}"

def add_scholar_links_to_latex(latex_text):
    # Chỉ gắn link cho phần References, giữ nguyên phần còn lại
    lines = latex_text.splitlines()
    new_lines = []
    in_refs = False
    for line in lines:
        if re.match(r"\\section\*?\{References\}", line, re.I):
            in_refs = True
            new_lines.append(line)
            continue
        if in_refs:
            if line.strip() == "" or line.startswith("\\"):
                new_lines.append(line)
                continue
            scholar_url = scholar_search_url(line.strip())
            # Gắn link dạng LaTeX: \href{url}{citation}
            new_lines.append(f"\\href{{{scholar_url}}}{{{line.strip()}}}")
        else:
            new_lines.append(line)
    # Đảm bảo có \usepackage{hyperref}
    latex = "\n".join(new_lines)
    if "\\usepackage{hyperref}" not in latex:
        latex = latex.replace("\\begin{document}", "\\usepackage{hyperref}\n\\begin{document}")
    return latex

def compile_latex_to_pdf(latex_code: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "article.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(latex_code)
        # Gọi pdflatex 2 lần để xử lý cross-ref
        try:
            for _ in range(2):
                subprocess.run(
                    ["pdflatex", "-interaction=nonstopmode", "article.tex"],
                    cwd=tmpdir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
            pdf_path = os.path.join(tmpdir, "article.pdf")
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            return pdf_bytes
        except Exception as e:
            raise RuntimeError("LaTeX compile error. Có thể thiếu pdflatex hoặc lỗi cú pháp LaTeX.") from e

# -----------------------------
# UI
# -----------------------------
st.title("🧠 Auto Research Writer — Gemini API (LaTeX PDF)")
st.caption("Sinh bài báo LaTeX chuẩn, tài liệu tham khảo tự động gắn link Google Scholar. Tự động xuất PDF.")

left, right = st.columns([1.5, 1])
with left:
    topic = st.text_input("Topic / Chủ đề", value="Green growth and sustainability")
    article_type = st.selectbox("Article type", list(ARTICLE_TYPES.keys()), index=0)
    outline = ARTICLE_TYPES[article_type]
    want_refs = st.checkbox("Ask model to include 'References' section", value=True)
    extra_instructions = st.text_area("Extra instructions (optional)", value="Use neutral, precise language and avoid unsupported claims.")

with right:
    model_name = st.selectbox("Gemini model", ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"], index=0)
    api_key = st.text_input("GEMINI_API_KEY", type="password", value="")
    seed = st.number_input("Random seed (optional)", value=0, step=1)

if seed:
    random.seed(int(seed)); np.random.seed(int(seed))

st.divider()

if st.button("🚀 Generate LaTeX Article & PDF", type="primary"):
    if not api_key:
        st.error("Please provide GEMINI_API_KEY.")
    else:
        try:
            prompt = compose_prompt_latex(topic, article_type, outline, extra_instructions, want_refs)
            latex = generate_with_gemini_api(api_key, prompt, model_name)
            if not latex.strip():
                raise RuntimeError("Empty response from Gemini API")
        except Exception as e:
            st.error(f"Gemini API error: {e}")
            latex = None

        if latex:
            # Gắn link Google Scholar vào References
            latex_with_links = add_scholar_links_to_latex(latex)
            st.subheader("📄 LaTeX Source")
            st.code(latex_with_links, language="latex")

            st.download_button("⬇️ Download LaTeX", data=latex_with_links, file_name="article.tex", mime="text/x-tex")

            # Tự động biên dịch PDF
            try:
                pdf_bytes = compile_latex_to_pdf(latex_with_links)
                st.download_button("⬇️ Download PDF", data=pdf_bytes, file_name="article.pdf", mime="application/pdf")
                st.success("✅ PDF đã được biên dịch tự động từ LaTeX!")
            except Exception as e:
                st.warning(f"Không thể biên dịch PDF tự động: {e}")
                st.info("Bạn có thể tải file .tex về và biên dịch trên Overleaf hoặc TeXstudio.")

else:
    st.info("Nhập chủ đề rồi bấm **Generate LaTeX Article & PDF**.")

with st.expander("ℹ️ Hướng dẫn"):
    st.markdown(
        """
- Ứng dụng này sinh bài báo LaTeX chuẩn, có thể biên dịch trực tiếp trên Overleaf hoặc TeXstudio.
- Phần References sẽ tự động gắn link Google Scholar cho từng tài liệu tham khảo.
- Nếu server có cài sẵn pdflatex, bạn có thể tải PDF trực tiếp. Nếu không, hãy tải file `.tex` về và biên dịch trên Overleaf.
        """
    )
