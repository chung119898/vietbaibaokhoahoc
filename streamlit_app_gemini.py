# app.py
import os
import io
import zipfile
from pathlib import Path
from datetime import date

import yaml
import streamlit as st

# --- Gemini setup ---
try:
    import google.generativeai as genai
except Exception:
    genai = None

# --- PDF / layout ---
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# -------- Paths / constants --------
APP_DIR = Path(__file__).parent if "__file__" in globals() else Path(".")
ASSETS_DIR = APP_DIR / "assets" / "fonts"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATE_FILE = APP_DIR / "TEMPLATE.md"
OUTPUT_DIR = APP_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# -------- Markdown template (để render bản xem trên UI; PDF render riêng) --------
DEFAULT_TEMPLATE = """---
title: "{{TITLE}}"
subtitle: "{{SUBTITLE}}"
author:
  - name: ""
date: "{{DATE}}"
lang: vi
---

# {{TITLE}}

**Tác giả**  
{{AUTHORS}}

## Tóm tắt
{{ABSTRACT}}

**Từ khóa:** {{KEYWORDS}}

---

## 1. Giới thiệu
{{INTRO}}

## 2. Phương pháp (PRISMA / Systematic Review)
{{METHODS}}

### 2.1 Sơ đồ PRISMA (mô tả ngắn)
{{PRISMA}}

## 3. Kết quả
{{RESULTS}}

## 4. Thảo luận
{{DISCUSSION}}

## 5. Kết luận
{{CONCLUSION}}

### Hạn chế
{{LIMITATIONS}}

---

## Lời cảm ơn
{{ACK}}

## Công bố dữ liệu / Mã nguồn
{{DATA_AVAIL}}

## Đạo đức
{{ETHICS}}

## Tài trợ
{{FUNDING}}

## Xung đột lợi ích
{{CONFLICTS}}

---

## Tài liệu tham khảo
{{REFERENCES}}
"""

# ===================== Utilities =====================

def ensure_template() -> str:
    if TEMPLATE_FILE.exists():
        return TEMPLATE_FILE.read_text(encoding="utf-8")
    return DEFAULT_TEMPLATE

def strip_code_fences(s: str) -> str:
    """Loại bỏ ```yaml/```yml/``` khỏi văn bản để parse YAML an toàn."""
    if not s:
        return s
    s = s.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        for i, ln in enumerate(lines):
            if ln.strip().startswith("```"):
                return "\n".join(lines[:i]).strip()
        s = "\n".join(lines)
    return s.replace("```yaml", "").replace("```yml", "").replace("```", "").strip()

def render_authors(authors):
    lines = []
    for a in authors or []:
        extras = []
        if a.get("affiliation"): extras.append(a["affiliation"])
        if a.get("email"): extras.append(f"✉ {a['email']}")
        if a.get("orcid"): extras.append(f"ORCID: {a['orcid']}")
        nm = a.get("name","")
        lines.append(f"- **{nm}**" + (" — " + " | ".join(extras) if extras else ""))
    return "\n".join(lines)

def render_refs_markdown(refs):
    out = []
    for r in refs or []:
        title = (r.get("title","") or "").rstrip(".")
        authors = "; ".join([f"{a.get('family','')}, {a.get('given','')}" for a in r.get("authors",[]) if a])
        year = r.get("date","n.d.")
        src = r.get("container","")
        doi = r.get("doi","") or r.get("url","")
        piece = f"{authors} ({year}). {title}. *{src}*."
        if doi: piece += f" {doi}"
        out.append(f"- {piece}")
    return "\n".join(out)

def fill_template(ctx: dict, tpl_text: str) -> str:
    rep = {
        "{{TITLE}}": ctx.get("meta", {}).get("title", ""),
        "{{SUBTITLE}}": ctx.get("meta", {}).get("subtitle", ""),
        "{{DATE}}": ctx.get("meta", {}).get("date", str(date.today())),
        "{{AUTHORS}}": render_authors(ctx.get("meta", {}).get("authors", [])),
        "{{ABSTRACT}}": ctx.get("abstract", {}).get("text", ""),
        "{{KEYWORDS}}": ", ".join(ctx.get("abstract", {}).get("keywords", []) or []),
        "{{INTRO}}": ctx.get("sections", {}).get("introduction", ""),
        "{{METHODS}}": ctx.get("sections", {}).get("methods", ""),
        "{{PRISMA}}": ctx.get("sections", {}).get("prisma", ""),
        "{{RESULTS}}": ctx.get("sections", {}).get("results", ""),
        "{{DISCUSSION}}": ctx.get("sections", {}).get("discussion", ""),
        "{{CONCLUSION}}": ctx.get("sections", {}).get("conclusion", ""),
        "{{LIMITATIONS}}": ctx.get("sections", {}).get("limitations", ""),
        "{{ACK}}": (ctx.get("acknowledgments", "") or "").strip(),
        "{{DATA_AVAIL}}": ctx.get("data_availability", ""),
        "{{ETHICS}}": ctx.get("ethics", ""),
        "{{FUNDING}}": ctx.get("funding", ""),
        "{{CONFLICTS}}": ctx.get("conflicts_of_interest", ""),
        "{{REFERENCES}}": render_refs_markdown(ctx.get("references", [])),
    }
    for k, v in rep.items():
        tpl_text = tpl_text.replace(k, "" if v is None else str(v))
    return tpl_text

def normalize_text(x):
    if x is None: return ""
    if isinstance(x, (int, float, date)): return str(x)
    return str(x)

# -------- PDF helpers --------

def _register_fonts():
    """
    Cố gắng dùng NotoSerif (Unicode tốt cho tiếng Việt).
    Đặt file:
      assets/fonts/NotoSerif-Regular.ttf
      assets/fonts/NotoSerif-Bold.ttf
      assets/fonts/NotoSerif-Italic.ttf (tuỳ)
    Nếu không có -> fallback Times-Roman (có thể mất dấu tiếng Việt).
    """
    regular = ASSETS_DIR / "NotoSerif-Regular.ttf"
    bold = ASSETS_DIR / "NotoSerif-Bold.ttf"
    italic = ASSETS_DIR / "NotoSerif-Italic.ttf"
    try:
        if regular.exists():
            pdfmetrics.registerFont(TTFont("NotoSerif", str(regular)))
            if bold.exists():
                pdfmetrics.registerFont(TTFont("NotoSerif-Bold", str(bold)))
            if italic.exists():
                pdfmetrics.registerFont(TTFont("NotoSerif-Italic", str(italic)))
            return "NotoSerif"
    except Exception:
        pass
    return "Times-Roman"  # fallback

def _styles(base_font):
    styles = getSampleStyleSheet()
    # Cleanup & redefine styles with our base font
    styles.add(ParagraphStyle(
        name="TitleVN", parent=styles["Title"], fontName=base_font if base_font=="Times-Roman" else "NotoSerif-Bold",
        fontSize=20, leading=24, alignment=1, spaceAfter=12
    ))
    styles.add(ParagraphStyle(
        name="SubtitleVN", parent=styles["Normal"], fontName=base_font, fontSize=12, leading=16, alignment=1, textColor=colors.grey
    ))
    styles.add(ParagraphStyle(
        name="MetaVN", parent=styles["Normal"], fontName=base_font, fontSize=10, leading=14, alignment=1
    ))
    styles.add(ParagraphStyle(
        name="H1", parent=styles["Heading1"], fontName=base_font if base_font=="Times-Roman" else "NotoSerif-Bold",
        fontSize=14, leading=18, spaceBefore=12, spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        name="H2", parent=styles["Heading2"], fontName=base_font if base_font=="Times-Roman" else "NotoSerif-Bold",
        fontSize=12, leading=16, spaceBefore=10, spaceAfter=4
    ))
    styles.add(ParagraphStyle(
        name="BodyVN", parent=styles["Normal"], fontName=base_font, fontSize=11, leading=16
    ))
    styles.add(ParagraphStyle(
        name="ItalicVN", parent=styles["Normal"], fontName=base_font, fontSize=11, leading=16, textColor=colors.black
    ))
    styles.add(ParagraphStyle(
        name="RefItem", parent=styles["Normal"], fontName=base_font, fontSize=10.5, leading=15, leftIndent=12, spaceAfter=3
    ))
    return styles

def _para(text, style):
    return Paragraph(normalize_text(text).replace("\n","<br/>"), style)

def build_pdf_story(ctx, styles):
    story = []
    meta = ctx.get("meta", {})
    abstract = ctx.get("abstract", {}) or {}
    sections = ctx.get("sections", {}) or {}

    # Title page
    story.append(_para(meta.get("title",""), styles["TitleVN"]))
    if meta.get("subtitle"):
        story.append(_para(meta.get("subtitle",""), styles["SubtitleVN"]))
    date_txt = meta.get("date", "")
    story.append(Spacer(1, 6))
    # Authors
    authors_txt = []
    for a in meta.get("authors", []) or []:
        nm = a.get("name","")
        aff = a.get("affiliation","")
        em = a.get("email","")
        oc = a.get("orcid","")
        line = nm
        extras = []
        if aff: extras.append(aff)
        if em: extras.append(f"✉ {em}")
        if oc: extras.append(f"ORCID: {oc}")
        if extras: line += " — " + " | ".join(extras)
        authors_txt.append(line)
    if authors_txt:
        story.append(_para("<br/>".join(authors_txt), styles["MetaVN"]))
    if date_txt:
        story.append(_para(normalize_text(date_txt), styles["MetaVN"]))
    story.append(Spacer(1, 12))

    # Abstract + Keywords
    story.append(_para("<b>Tóm tắt</b>", styles["H1"]))
    story.append(_para(abstract.get("text",""), styles["BodyVN"]))
    keys = abstract.get("keywords") or []
    if keys:
        story.append(Spacer(1,6))
        story.append(_para("<i>Từ khóa:</i> " + ", ".join(keys), styles["BodyVN"]))
    story.append(Spacer(1, 10))

    # Sections
    def add_section(title, key):
        content = sections.get(key,"")
        if content:
            story.append(_para(f"<b>{title}</b>", styles["H1"]))
            story.append(_para(content, styles["BodyVN"]))
            story.append(Spacer(1,6))

    add_section("1. Giới thiệu", "introduction")
    add_section("2. Phương pháp (PRISMA / Systematic Review)", "methods")
    if sections.get("prisma"):
        story.append(_para("2.1 Sơ đồ PRISMA (mô tả ngắn)", styles["H2"]))
        story.append(_para(sections.get("prisma",""), styles["BodyVN"]))
        story.append(Spacer(1,6))
    add_section("3. Kết quả", "results")
    add_section("4. Thảo luận", "discussion")
    add_section("5. Kết luận", "conclusion")
    if sections.get("limitations"):
        story.append(_para("Hạn chế", styles["H2"]))
        story.append(_para(sections.get("limitations",""), styles["BodyVN"]))
        story.append(Spacer(1,6))

    # Other statements
    def maybe_block(title, key):
        v = ctx.get(key, "")
        if v:
            story.append(_para(f"<b>{title}</b>", styles["H1"]))
            story.append(_para(v, styles["BodyVN"]))
            story.append(Spacer(1,6))
    maybe_block("Lời cảm ơn", "acknowledgments")
    maybe_block("Công bố dữ liệu / Mã nguồn", "data_availability")
    maybe_block("Đạo đức", "ethics")
    maybe_block("Tài trợ", "funding")
    maybe_block("Xung đột lợi ích", "conflicts_of_interest")

    # References
    refs = ctx.get("references", []) or []
    if refs:
        story.append(_para("<b>Tài liệu tham khảo</b>", styles["H1"]))
        for i, r in enumerate(refs, 1):
            title = (r.get("title","") or "").rstrip(".")
            authors = "; ".join([f"{a.get('family','')}, {a.get('given','')}" for a in r.get("authors",[]) if a])
            year = r.get("date","n.d.")
            src = r.get("container","")
            doi = r.get("doi","") or r.get("url","")
            piece = f"{i}. {authors} ({year}). {title}. <i>{src}</i>."
            if doi: piece += f" {doi}"
            story.append(_para(piece, styles["RefItem"]))
    return story

def save_pdf(ctx, out_path: Path):
    base_font = _register_fonts()
    styles = _styles(base_font)
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=44, rightMargin=44, topMargin=56, bottomMargin=56
    )
    story = build_pdf_story(ctx, styles)
    doc.build(story)

# ===================== Streamlit UI =====================

st.set_page_config(page_title="Gemini → Sinh bài báo & Xuất PDF (IMRaD + PRISMA)", layout="wide")
st.title("🧪 Gemini → Viết bài báo khoa học (đa tiêu đề) → Xuất PDF")

with st.sidebar:
    st.header("Thiết lập")
    # Secrets lấy sẵn nếu có
    default_key = ""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            default_key = st.secrets.get("GEMINI_API_KEY","")
    except Exception:
        pass
    api_key = st.text_input("GEMINI_API_KEY", value=default_key, type="password")
    model_name = st.selectbox("Model", ["gemini-1.5-flash", "gemini-1.5-pro"], index=0)
    ref_count = st.number_input("Số tài liệu tham khảo (gợi ý)", min_value=5, max_value=60, value=20)
    language = st.selectbox("Ngôn ngữ đầu ra", ["vi", "en"], index=0)
    st.caption("Khuyên dùng Secrets trên Streamlit Cloud: Settings → Secrets → GEMINI_API_KEY")

col1, col2 = st.columns([1,2])

with col1:
    st.subheader("1) Danh sách tiêu đề (mỗi dòng 1 tiêu đề)")
    titles_text = st.text_area("Nhập tiêu đề...", height=200, placeholder="Ví dụ:\nTổng quan hệ thống về tăng trưởng xanh tại Việt Nam\nTác động của chuyển dịch năng lượng ở Đông Nam Á")
    subtitle = st.text_input("Phụ đề (áp cho tất cả, có thể trống)", value="")
    keywords = st.text_input("Từ khóa chung (phân tách bởi dấu phẩy)", value="tăng trưởng xanh, PRISMA, Việt Nam, tổng quan hệ thống")
    review_type = st.selectbox("Loại bài", ["Systematic Review (PRISMA)", "Scoping Review", "Original Research"], index=0)
    run_btn = st.button("🚀 Sinh bài báo & Xuất PDF")

with col2:
    st.subheader("2) Xem nhanh YAML & Markdown")
    tabs_area = st.empty()
    st.subheader("3) Tải kết quả")
    zip_dl_area = st.empty()

if run_btn:
    titles = [t.strip() for t in (titles_text or "").splitlines() if t.strip()]
    if not genai:
        st.error("Chưa cài google-generativeai. Thêm vào requirements.txt và deploy lại.")
    elif not api_key:
        st.error("Cần nhập GEMINI_API_KEY (Sidebar).")
    elif not titles:
        st.error("Cần ít nhất 1 tiêu đề.")
    else:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)

            sys_inst = (
                "Bạn là trợ lý biên tập khoa học. Hãy xuất RA DUY NHẤT một YAML hợp lệ cho bài báo theo IMRaD + PRISMA. "
                "TUYỆT ĐỐI KHÔNG dùng code fence, KHÔNG dùng ```yaml hay ``` bất kỳ. "
                "Trả về các khóa bắt buộc: meta(title, subtitle, date, authors[]), abstract(text, keywords[]), "
                "sections(introduction, methods, prisma, results, discussion, conclusion, limitations), acknowledgments, "
                "data_availability, ethics, funding, conflicts_of_interest, references[]. "
                "references: mỗi mục gồm type (journal_article|book|web_article|conference_paper), authors[family,given], "
                "date (YYYY hoặc YYYY-MM hoặc YYYY-MM-DD), title, container, volume, issue, pages, doi hoặc url. "
                "Ngôn ngữ phải đúng tham số 'language'."
            )

            # Mỗi tiêu đề sinh 1 YAML, render ra PDF + hiển thị YAML/MD
            tabs = st.tabs([f"Bài {i+1}" for i in range(len(titles))])
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for idx, title in enumerate(titles):
                    prompt = f"""
Hãy viết YAML cho bài báo khoa học theo định dạng trên. Thông tin đầu vào:
- title: "{title}"
- subtitle: "{subtitle}"
- desired_language: "{language}"
- keywords: "{keywords}"
- review_type: "{review_type}"
- reference_count_hint: {int(ref_count)}

Yêu cầu nội dung:
- Abstract ~ 200-300 từ.
- Methods nêu rõ PICOS, nguồn dữ liệu, chiến lược truy vấn, tiêu chí đưa vào/loại ra, quy trình sàng lọc (PRISMA).
- Results tổng hợp định lượng/định tính, có xu hướng theo năm và chủ đề.
- Discussion nêu ý nghĩa, so sánh với nghiên cứu trước, hàm ý chính sách/thực tiễn.
- Conclusion + Limitations rõ ràng.
- Tạo {int(ref_count)} tài liệu tham khảo giả-lập hợp lý (không cần tồn tại thực), đúng cấu trúc trường yêu cầu.
Chỉ trả về YAML thuần, không kèm markdown fences.
                    """.strip()

                    resp = model.generate_content([sys_inst, prompt])
                    raw_text = (getattr(resp, "text", None) or "").strip()
                    text = strip_code_fences(raw_text)

                    # parse YAML
                    ctx = yaml.safe_load(text) or {}
                    # ensure minimal meta
                    ctx.setdefault("meta", {})
                    ctx["meta"]["title"] = ctx["meta"].get("title") or title
                    ctx["meta"]["subtitle"] = ctx["meta"].get("subtitle") or subtitle
                    ctx["meta"]["date"] = ctx["meta"].get("date") or str(date.today())

                    # Render Markdown demo
                    md = fill_template(ctx, ensure_template())

                    with tabs[idx]:
                        st.caption(f"Tiêu đề: **{title}**")
                        st.markdown("**YAML sinh ra**")
                        st.code(yaml.safe_dump(ctx, allow_unicode=True, sort_keys=False), language="yaml")
                        st.markdown("**Xem nhanh Markdown**")
                        st.markdown(md)

                    # Save PDF
                    pdf_name = f"paper_{idx+1}.pdf"
                    pdf_path = OUTPUT_DIR / pdf_name
                    save_pdf(ctx, pdf_path)

                    # Add to zip
                    zf.write(str(pdf_path), arcname=pdf_name)

            zip_buf.seek(0)
            zip_dl_area.download_button(
                "⬇️ Tải tất cả PDF (ZIP)",
                data=zip_buf.read(),
                file_name="papers.zip",
                mime="application/zip"
            )
            st.success("Đã sinh bài và xuất PDF cho tất cả tiêu đề!")
        except Exception as e:
            st.error(f"Lỗi xử lý: {e}")

# --- Footer: hướng dẫn font ---
with st.expander("⚠️ Lưu ý hiển thị tiếng Việt trong PDF"):
    st.markdown(
        "- Để PDF hiển thị tiếng Việt chuẩn, hãy đặt font **NotoSerif** trong `assets/fonts/` với các file:\n"
        "  - `NotoSerif-Regular.ttf`\n"
        "  - `NotoSerif-Bold.ttf`\n"
        "  - (tuỳ chọn) `NotoSerif-Italic.ttf`\n"
        "- Nếu thiếu font, app sẽ fallback **Times-Roman** (có thể lỗi dấu)."
    )
