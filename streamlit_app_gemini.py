# app.py
import io
import zipfile
from pathlib import Path
from datetime import date

import yaml
import streamlit as st

# --- Gemini ---
try:
    import google.generativeai as genai
except Exception:
    genai = None

# --- PDF / layout ---
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak,
    NextPageTemplate, FrameBreak
)
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

APP_DIR = Path(__file__).parent if "__file__" in globals() else Path(".")
ASSETS_FONTS = APP_DIR / "assets" / "fonts"
ASSETS_FONTS.mkdir(parents=True, exist_ok=True)
OUT_DIR = APP_DIR / "outputs"; OUT_DIR.mkdir(exist_ok=True, parents=True)

# ---------- Prompt “PhD-level” ----------
def phd_system_instruction():
    return (
        "Bạn là trợ lý biên tập học thuật cấp độ tiến sĩ. Hãy TRẢ VỀ DUY NHẤT một YAML hợp lệ "
        "mô tả bản thảo theo chuẩn IMRaD + PRISMA, văn phong học thuật, khách quan, súc tích, "
        "tránh suy diễn vô căn cứ, có nhấn mạnh đóng góp, hạn chế, và hàm ý chính sách.\n"
        "Tuyệt đối KHÔNG dùng code fence (```yaml, ```), chỉ trả về YAML thuần.\n"
        "YAML cần chứa các khóa:\n"
        "meta: {title, subtitle, date, authors:[{name, affiliation?, email?, orcid?}]}\n"
        "abstract: {text (~220-280 từ), keywords: [..]}\n"
        "sections: {introduction, methods, prisma, results, discussion, conclusion, limitations}\n"
        "acknowledgments, data_availability, ethics, funding, conflicts_of_interest\n"
        "references: danh sách mục tham khảo có: type, title, container, date, authors[{family,given}], "
        "volume?, issue?, pages?, doi? hoặc url?\n"
        "Lưu ý: nội dung phải thống nhất, có dẫn nguồn trong văn bản (tên-năm) khi cần; "
        "PRISMA mô tả quy trình sàng lọc; Methods nêu PICOS & chiến lược truy vấn; Results có xu hướng & bảng/điểm nhấn "
        "(dưới dạng mô tả, không cần số liệu thật); Discussion so sánh với nghiên cứu trước; Conclusion rõ ràng; Limitations cụ thể.\n"
        "Ngôn ngữ đầu ra đúng tham số 'language'."
    )

def make_user_prompt(title, subtitle, language, keywords, review_type, ref_count):
    return f"""
Sinh YAML học thuật cho bài báo:
- title: "{title}"
- subtitle: "{subtitle}"
- desired_language: "{language}"
- keywords: "{keywords}"
- review_type: "{review_type}"
- reference_count_hint: {int(ref_count)}

Yêu cầu:
- Văn phong tiến sĩ (phản biện, chặt chẽ, dùng thuật ngữ chuẩn).
- Abstract 220–280 từ; từ khóa 5–8 mục.
- Methods: PICOS, nguồn CSDL, chuỗi truy vấn ví dụ, tiêu chí đưa vào/loại ra, PRISMA (mô tả).
- Results: tổng hợp định lượng/định tính, xu hướng theo giai đoạn, cụm chủ đề.
- Discussion: ý nghĩa, so sánh, hàm ý chính sách/thực tiễn.
- Conclusion + Limitations: ngắn gọn, thẳng.
- references: ghi đủ trường như yêu cầu (có thể giả-lập hợp lý), ưu tiên có DOI.
Chỉ trả về YAML thuần, không kèm chữ giải thích.
""".strip()

# ---------- YAML utils ----------
def strip_code_fences(s: str) -> str:
    if not s: return s
    s = s.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        for i, ln in enumerate(lines):
            if ln.strip().startswith("```"):
                return "\n".join(lines[:i]).strip()
        s = "\n".join(lines)
    return s.replace("```yaml","").replace("```yml","").replace("```","").strip()

def ensure_meta(ctx, title, subtitle):
    ctx.setdefault("meta", {})
    ctx["meta"]["title"] = ctx["meta"].get("title") or title
    ctx["meta"]["subtitle"] = ctx["meta"].get("subtitle") or subtitle
    # Nếu đã parse thành datetime.date thì convert về chuỗi
    d = ctx["meta"].get("date")
    ctx["meta"]["date"] = str(d) if d else str(date.today())
    if not ctx["meta"].get("authors"):
        ctx["meta"]["authors"] = [{"name":"", "affiliation":"", "email":""}]

# ---------- Styles & fonts ----------
def register_fonts():
    try:
        reg = ASSETS_FONTS/"NotoSerif-Regular.ttf"
        bold = ASSETS_FONTS/"NotoSerif-Bold.ttf"
        if reg.exists():
            pdfmetrics.registerFont(TTFont("NotoSerif", str(reg)))
            if bold.exists():
                pdfmetrics.registerFont(TTFont("NotoSerif-Bold", str(bold)))
            return "NotoSerif"
    except Exception:
        pass
    return "Times-Roman"

def make_styles(base_font):
    s = getSampleStyleSheet()
    # Tiêu đề & heading
    s.add(ParagraphStyle(name="TitleVN", parent=s["Title"],
                         fontName="NotoSerif-Bold" if base_font!="Times-Roman" else base_font,
                         fontSize=20, leading=24, alignment=1, spaceAfter=10))
    s.add(ParagraphStyle(name="SubtitleVN", parent=s["Normal"],
                         fontName=base_font, fontSize=12, leading=16, alignment=1, textColor=colors.grey))
    s.add(ParagraphStyle(name="MetaVN", parent=s["Normal"],
                         fontName=base_font, fontSize=10.5, leading=14, alignment=1))
    s.add(ParagraphStyle(name="H1", parent=s["Heading1"],
                         fontName="NotoSerif-Bold" if base_font!="Times-Roman" else base_font,
                         fontSize=14, leading=18, spaceBefore=10, spaceAfter=6))
    s.add(ParagraphStyle(name="H2", parent=s["Heading2"],
                         fontName="NotoSerif-Bold" if base_font!="Times-Roman" else base_font,
                         fontSize=12, leading=16, spaceBefore=8, spaceAfter=4))
    s.add(ParagraphStyle(name="BodyVN", parent=s["Normal"],
                         fontName=base_font, fontSize=11, leading=16))
    s.add(ParagraphStyle(name="RefItem", parent=s["Normal"],
                         fontName=base_font, fontSize=10.5, leading=15, leftIndent=12, spaceAfter=2))
    s.add(ParagraphStyle(name="SmallGrey", parent=s["Normal"],
                         fontName=base_font, fontSize=9, leading=12, textColor=colors.grey))
    return s

# ---------- PDF helpers (2 cột) ----------
def draw_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Roman", 9)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(doc.pagesize[0]-doc.rightMargin, 20, f"{doc.page}")
    canvas.restoreState()

def p(txt, style):  # chuyển \n -> <br/>
    return Paragraph(str(txt or "").replace("\n","<br/>"), style)

def build_first_page(ctx, styles):
    story = []
    m = ctx.get("meta", {})
    abs_ = ctx.get("abstract", {}) or {}
    # Title & metadata (full width)
    story += [
        p(m.get("title",""), styles["TitleVN"]),
        p(m.get("subtitle",""), styles["SubtitleVN"]) if m.get("subtitle") else Spacer(1,2),
        Spacer(1,6)
    ]
    # Authors
    auth_lines = []
    for a in m.get("authors") or []:
        nm = a.get("name","")
        extras = [x for x in [a.get("affiliation",""), f"✉ {a.get('email','')}" if a.get("email") else "", f"ORCID: {a.get('orcid','')}" if a.get("orcid") else ""] if x]
        line = nm + (" — " + " | ".join(extras) if extras else "")
        auth_lines.append(line)
    if auth_lines:
        story.append(p("<br/>".join(auth_lines), styles["MetaVN"]))
    story.append(p(str(m.get("date","")), styles["SmallGrey"]))
    story.append(Spacer(1,10))
    # Abstract
    story += [p("Tóm tắt", styles["H1"]), p(abs_.get("text",""), styles["BodyVN"])]
    if abs_.get("keywords"):
        story += [Spacer(1,4), p("<i>Từ khóa:</i> " + ", ".join(abs_["keywords"]), styles["BodyVN"])]
    story += [Spacer(1,8)]
    return story

def build_body_two_cols(ctx, styles):
    S = []
    sec = ctx.get("sections", {}) or {}

    def add_block(h, key, hstyle="H1"):
        if sec.get(key):
            S.append(p(h, styles[hstyle])); S.append(p(sec.get(key,""), styles["BodyVN"])); S.append(Spacer(1,6))

    add_block("1. Giới thiệu", "introduction")
    add_block("2. Phương pháp (PRISMA / Systematic Review)", "methods")
    if sec.get("prisma"):
        S.append(p("2.1 Sơ đồ PRISMA (mô tả)", styles["H2"])); S.append(p(sec.get("prisma",""), styles["BodyVN"])); S.append(Spacer(1,6))
    add_block("3. Kết quả", "results")
    add_block("4. Thảo luận", "discussion")
    add_block("5. Kết luận", "conclusion")
    if sec.get("limitations"):
        S.append(p("Hạn chế", styles["H2"])); S.append(p(sec.get("limitations",""), styles["BodyVN"])); S.append(Spacer(1,6))

    # Statements
    def opt_block(h, key):
        v = ctx.get(key, "")
        if v:
            S.append(p(h, styles["H1"])); S.append(p(v, styles["BodyVN"])); S.append(Spacer(1,6))
    opt_block("Lời cảm ơn", "acknowledgments")
    opt_block("Công bố dữ liệu / Mã nguồn", "data_availability")
    opt_block("Đạo đức", "ethics")
    opt_block("Tài trợ", "funding")
    opt_block("Xung đột lợi ích", "conflicts_of_interest")

    # References
    refs = ctx.get("references") or []
    if refs:
        S.append(p("Tài liệu tham khảo", styles["H1"]))
        for i, r in enumerate(refs, 1):
            title = (r.get("title","") or "").rstrip(".")
            authors = "; ".join([f"{a.get('family','')}, {a.get('given','')}" for a in r.get("authors",[]) if a])
            year = r.get("date","n.d.")
            src = r.get("container","")
            doi = r.get("doi","") or r.get("url","")
            text = f"{i}. {authors} ({year}). {title}. <i>{src}</i>."
            if doi: text += f" {doi}"
            S.append(p(text, styles["RefItem"]))
    return S

def export_pdf_two_cols(ctx, out_path: Path):
    base_font = register_fonts()
    styles = make_styles(base_font)

    doc = BaseDocTemplate(str(out_path), pagesize=A4,
                          leftMargin=44, rightMargin=44, topMargin=56, bottomMargin=56)

    # Frames: First page (full width), then 2 columns
    frame_full = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="full")
    gap = 14
    col_w = (doc.width - gap) / 2
    frame_l = Frame(doc.leftMargin, doc.bottomMargin, col_w, doc.height, id="col1")
    frame_r = Frame(doc.leftMargin + col_w + gap, doc.bottomMargin, col_w, doc.height, id="col2")

    doc.addPageTemplates([
        PageTemplate(id="First", frames=[frame_full], onPage=draw_footer),
        PageTemplate(id="TwoCol", frames=[frame_l, frame_r], onPage=draw_footer),
    ])

    story = []
    story += build_first_page(ctx, styles)
    story += [NextPageTemplate("TwoCol"), PageBreak()]
    story += build_body_two_cols(ctx, styles)

    doc.build(story)

# ---------- Streamlit UI ----------
st.set_page_config(page_title="PhD-style Papers (IMRaD + PRISMA) → PDF 2 cột", layout="wide")
st.title("🧪 Gemini → Viết bài học thuật kiểu 'tiến sỹ' → Xuất PDF 2 cột")

with st.sidebar:
    st.header("Thiết lập")
    default_key = ""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            default_key = st.secrets.get("GEMINI_API_KEY","")
    except Exception:
        pass
    api_key = st.text_input("GEMINI_API_KEY", value=default_key, type="password")
    model_name = st.selectbox("Model", ["gemini-1.5-pro", "gemini-1.5-flash"], index=0)
    ref_count = st.number_input("Số tài liệu tham khảo (gợi ý)", min_value=8, max_value=80, value=25)
    language = st.selectbox("Ngôn ngữ", ["vi", "en"], index=0)
    st.caption("Bố cục PDF 2 cột (title/abstract full-width) lấy cảm hứng từ bài mẫu bạn gửi.")

col1, col2 = st.columns([1,2])
with col1:
    st.subheader("1) Nhập tiêu đề (mỗi dòng 1 tiêu đề)")
    titles_text = st.text_area("Tiêu đề...", height=180, placeholder="Ví dụ:\nTổng quan hệ thống về tăng trưởng xanh tại Việt Nam")
    subtitle = st.text_input("Phụ đề (tuỳ chọn)")
    keywords = st.text_input("Từ khóa chung (phân tách bởi dấu phẩy)",
                             value="tăng trưởng xanh, PRISMA, Việt Nam, tổng quan hệ thống")
    review_type = st.selectbox("Loại bài", ["Systematic Review (PRISMA)", "Scoping Review", "Original Research"], index=0)
    run_btn = st.button("🚀 Sinh YAML & Xuất PDF 2 cột")

with col2:
    st.subheader("2) Xem nhanh YAML")
    tabs_area = st.empty()
    st.subheader("3) Tải về")
    zip_area = st.empty()

if run_btn:
    titles = [t.strip() for t in (titles_text or "").splitlines() if t.strip()]
    if not genai:
        st.error("Chưa cài google-generativeai. Thêm vào requirements.txt và deploy lại.")
    elif not api_key:
        st.error("Cần nhập GEMINI_API_KEY.")
    elif not titles:
        st.error("Cần ít nhất 1 tiêu đề.")
    else:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)

            tabs = st.tabs([f"Bài {i+1}" for i in range(len(titles))])
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for i, title in enumerate(titles):
                    sys_inst = phd_system_instruction()
                    user_prompt = make_user_prompt(title, subtitle, language, keywords, review_type, ref_count)

                    resp = model.generate_content([sys_inst, user_prompt])
                    raw_text = (getattr(resp, "text", None) or "").strip()
                    text = strip_code_fences(raw_text)
                    ctx = yaml.safe_load(text) or {}
                    ensure_meta(ctx, title, subtitle)

                    # Show YAML & Export PDF
                    with tabs[i]:
                        st.code(yaml.safe_dump(ctx, allow_unicode=True, sort_keys=False), language="yaml")

                    pdf_name = f"paper_{i+1}.pdf"
                    pdf_path = OUT_DIR / pdf_name
                    export_pdf_two_cols(ctx, pdf_path)
                    zf.write(str(pdf_path), arcname=pdf_name)

            zip_buf.seek(0)
            zip_area.download_button(
                "⬇️ Tải tất cả PDF (ZIP)",
                data=zip_buf.read(),
                file_name="papers_phd_twocol.zip",
                mime="application/zip"
            )
            st.success("Đã sinh bài học thuật & xuất PDF 2 cột.")
        except Exception as e:
            st.error(f"Lỗi xử lý: {e}")
            # Hiển thị raw để debug nếu YAML lỗi
            try:
                st.code(raw_text, language="yaml")
            except Exception:
                pass

# Gợi ý font để hiển thị tiếng Việt
with st.expander("⚠️ Font tiếng Việt cho PDF"):
    st.markdown(
        "- Đặt các file font vào `assets/fonts/`:\n"
        "  - `NotoSerif-Regular.ttf`\n"
        "  - `NotoSerif-Bold.ttf`\n"
        "- Nếu thiếu, PDF sẽ fallback Times-Roman (có thể mất dấu)."
    )
