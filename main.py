import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import random
import io
import textwrap
import re
import requests
import json

# -----------------------------
# Page config & helpers
# -----------------------------
st.set_page_config(page_title="Auto Research Writer (Gemini API)", page_icon="🧠", layout="wide")
st.markdown("""
<style>
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# App settings
# -----------------------------
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

def compose_prompt(topic: str, article_type: str, outline: list, words_per_section: int,
                   extra_instructions: str, want_refs: bool):
    outline_block = "\n".join(f"## {i+1}. {sec}" for i, sec in enumerate(outline))
    refs_guidance = (
        "Include a final section 'References' with plausible APA-style citations (author, year, title, venue). "
        "Do NOT invent DOIs or URLs; if uncertain, mark as 'retrieval needed'."
    ) if want_refs else ""
    return f"""
{DEFAULT_PROMPT_INSTRUCTIONS}
{extra_instructions}

Write a {article_type} on the topic: "{topic}".
Target ~{words_per_section} words per section. Keep paragraphs short and readable.
Use the following outline exactly and write content under each header:
{outline_block}

Tone: scholarly but accessible. Avoid filler. Where evidence is uncertain, say so explicitly.
{refs_guidance}

Return markdown with level-2 headers matching the outline, plus a top-level H1 title and an author line placeholder.
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

def parse_markdown_sections(md_text: str):
    title = "Untitled"
    authors = "Anonymous"
    lines = md_text.splitlines()
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
    for ln in lines[:10]:
        if ln.lower().startswith("**authors**") or ln.lower().startswith("authors:"):
            authors = re.sub(r"(?i)\*\*?authors\*\*?:?\s*", "", ln).strip()
    sections = []
    cur = None
    buf = []
    for ln in lines:
        if ln.startswith("## "):
            if cur is not None:
                sections.append((cur, "\n".join(buf).strip()))
            cur = ln[3:].strip()
            buf = []
        else:
            buf.append(ln)
    if cur is not None:
        sections.append((cur, "\n".join(buf).strip()))
    return title, authors, sections

def check_reference_real(ref_text):
    # Đơn giản: nếu có "retrieval needed" hoặc "unknown" thì coi là bịa
    if re.search(r"retrieval needed|unknown|n\.d\.|no author", ref_text, re.I):
        return False
    return True

def analyze_references(md_text):
    refs = []
    in_refs = False
    for line in md_text.splitlines():
        if re.match(r"^##?\s*References", line, re.I):
            in_refs = True
            continue
        if in_refs:
            if line.strip() == "" or line.startswith("#"):
                continue
            refs.append(line.strip())
    real_refs = [r for r in refs if check_reference_real(r)]
    fake_refs = [r for r in refs if not check_reference_real(r)]
    return real_refs, fake_refs

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
except Exception:
    Document = None

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas
except Exception:
    rl_canvas = None

def export_docx(md_text: str) -> bytes:
    if Document is None:
        raise RuntimeError("python-docx not installed")
    title, authors, sections = parse_markdown_sections(md_text)
    doc = Document()
    doc.add_heading(title, 0)
    p = doc.add_paragraph(f"Authors: {authors}")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    doc.add_paragraph(datetime.now().strftime("%Y-%m-%d"))
    doc.add_paragraph("")
    for sec, body in sections:
        doc.add_heading(sec, level=1)
        for para in body.split("\n\n"):
            doc.add_paragraph(para)
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

def export_pdf_basic(md_text: str) -> bytes:
    if rl_canvas is None:
        raise RuntimeError("reportlab not installed")
    title, authors, sections = parse_markdown_sections(md_text)
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    def draw_wrapped(text, x, y, max_width):
        wrapper = textwrap.TextWrapper(width=95)
        for line in text.split("\n"):
            for sub in wrapper.wrap(line):
                nonlocal_y[0] -= 14
                if nonlocal_y[0] < 72:
                    c.showPage(); nonlocal_y[0] = height - 72
                c.drawString(x, nonlocal_y[0], sub)

    nonlocal_y = [height - 72]
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width/2, nonlocal_y[0], title)
    c.setFont("Helvetica", 10)
    nonlocal_y[0] -= 24
    c.drawCentredString(width/2, nonlocal_y[0], f"Authors: {authors}")
    nonlocal_y[0] -= 24
    c.drawCentredString(width/2, nonlocal_y[0], datetime.now().strftime("%Y-%m-%d"))

    c.setFont("Helvetica", 11)
    for sec, body in sections:
        nonlocal_y[0] -= 28
        if nonlocal_y[0] < 100:
            c.showPage(); nonlocal_y[0] = height - 72; c.setFont("Helvetica", 11)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, nonlocal_y[0], sec)
        c.setFont("Helvetica", 11)
        nonlocal_y[0] -= 10
        draw_wrapped(body, 72, nonlocal_y[0], width - 144)

    c.showPage()
    c.save()
    return buf.getvalue()

# -----------------------------
# UI
# -----------------------------
st.title("🧠 Auto Research Writer — Gemini API Only")
st.caption("Generate academically-styled articles using Google Gemini API. Export to DOCX/PDF.")

left, right = st.columns([1.5, 1])
with left:
    topic = st.text_input("Topic / Chủ đề", value="Green growth and sustainability")
    article_type = st.selectbox("Article type", list(ARTICLE_TYPES.keys()), index=0)
    outline = ARTICLE_TYPES[article_type]
    words_per_section = st.slider("~Words per section", 120, 600, 220, step=20)
    want_refs = st.checkbox("Ask model to include 'References' section", value=True)
    extra_instructions = st.text_area("Extra instructions (optional)", value="Use neutral, precise language and avoid unsupported claims.")
    require_real_refs = st.checkbox("Chỉ chấp nhận bài viết có nguồn tham khảo thực (không bịa)", value=False)

with right:
    model_name = st.selectbox("Gemini model", ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"], index=0)
    api_key = st.text_input("GEMINI_API_KEY", type="password", value="AIzaSyAiE7jIUSMxYSDebCdXDgxOq4mWhMuXiQE")
    seed = st.number_input("Random seed (optional)", value=0, step=1)
    include_demo_chart = st.checkbox("Add demo chart (synthetic)", value=False)

if seed:
    random.seed(int(seed)); np.random.seed(int(seed))

st.divider()

if st.button("🚀 Generate Article", type="primary"):
    if not api_key:
        st.error("Please provide GEMINI_API_KEY.")
    else:
        try:
            prompt = compose_prompt(topic, article_type, outline, words_per_section, extra_instructions, want_refs)
            md = generate_with_gemini_api(api_key, prompt, model_name)
            if not md.strip():
                raise RuntimeError("Empty response from Gemini API")
        except Exception as e:
            st.error(f"Gemini API error: {e}")
            md = None

        if md:
            st.markdown(md)

            # Kiểm tra nguồn tham khảo thực
            if want_refs and require_real_refs:
                real_refs, fake_refs = analyze_references(md)
                if not fake_refs and real_refs:
                    st.success("✅ Bài viết chuẩn có nguồn tham khảo thực (không bịa).")
                elif fake_refs:
                    st.warning(f"⚠️ Một số nguồn tham khảo có thể không xác thực hoặc bị bịa:\n\n" +
                               "\n".join(f"- {r}" for r in fake_refs))
                else:
                    st.info("Không phát hiện nguồn tham khảo trong bài.")

            if include_demo_chart:
                st.subheader("Figure: Demonstration Time Series")
                x = pd.date_range(datetime.now().date().replace(day=1), periods=36, freq="MS")
                y1 = np.cumsum(np.random.randn(len(x))) + 10
                y2 = y1 + np.random.randn(len(x)) * 0.5 + 2
                fig_df = pd.DataFrame({"Date": x, "Baseline": y1, "Proposed": y2}).set_index("Date")
                st.line_chart(fig_df, use_container_width=True)
                st.caption("Synthetic data for illustrative purposes only.")

            st.divider()
            st.download_button("⬇️ Download Markdown", data=md, file_name="article.md", mime="text/markdown")

            try:
                docx_bytes = export_docx(md)
                st.download_button("⬇️ Download DOCX", data=docx_bytes,
                    file_name="article.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            except Exception as e:
                st.info(f"DOCX export unavailable: {e}")

            try:
                pdf_bytes = export_pdf_basic(md)
                st.download_button("⬇️ Download PDF", data=pdf_bytes, file_name="article.pdf", mime="application/pdf")
            except Exception as e:
                st.info(f"PDF export unavailable: {e}")

else:
    st.info("Nhập chủ đề rồi bấm **Generate Article**.")

with st.expander("ℹ️ Setup (Gemini API)"):
    st.markdown(
        "Ứng dụng này chỉ sử dụng Gemini API trực tiếp qua HTTP. Không hỗ trợ chế độ offline."
    )
