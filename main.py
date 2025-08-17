import os
import yaml
import streamlit as st
from datetime import date
from pathlib import Path

# -------- Gemini setup --------
try:
    import google.generativeai as genai
except Exception:
    genai = None

TEMPLATE_FILE = Path("TEMPLATE.md")
OUTPUT_MD = Path("paper.md")

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

def render_authors(authors):
    lines = []
    for a in authors or []:
        extras = []
        if a.get("affiliation"): extras.append(a["affiliation"])
        if a.get("email"): extras.append(f"✉ {a['email']}")
        if a.get("orcid"): extras.append(f"ORCID: {a['orcid']}")
        lines.append(f"- **{a.get('name','')}**" + (" — " + " | ".join(extras) if extras else ""))
    return "\n".join(lines)

def render_refs(refs):
    out = []
    for r in refs or []:
        # rất giản lược, bạn đã có apa_reference_formatter.py thì có thể import để format đẹp hơn
        title = r.get("title","").rstrip(".")
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
        "{{RESULTS}}": ctx.get("sections", {}).get("results", ""),
        "{{DISCUSSION}}": ctx.get("sections", {}).get("discussion", ""),
        "{{CONCLUSION}}": ctx.get("sections", {}).get("conclusion", ""),
        "{{LIMITATIONS}}": ctx.get("sections", {}).get("limitations", ""),
        "{{ACK}}": (ctx.get("acknowledgments", "") or "").strip(),
        "{{DATA_AVAIL}}": ctx.get("data_availability", ""),
        "{{ETHICS}}": ctx.get("ethics", ""),
        "{{FUNDING}}": ctx.get("funding", ""),
        "{{CONFLICTS}}": ctx.get("conflicts_of_interest", ""),
        "{{PRISMA}}": ctx.get("sections", {}).get("prisma", ""),
        "{{REFERENCES}}": render_refs(ctx.get("references", [])),
    }
    for k, v in rep.items():
        tpl_text = tpl_text.replace(k, v)
    return tpl_text

def ensure_template() -> str:
    if TEMPLATE_FILE.exists():
        return TEMPLATE_FILE.read_text(encoding="utf-8")
    return DEFAULT_TEMPLATE

# ---------- Streamlit UI ----------
st.set_page_config(page_title="Gemini → Viết bài báo IMRaD + PRISMA", layout="wide")
st.title("🧪 Gemini: Tạo bài báo khoa học từ tiêu đề")

with st.sidebar:
    st.header("Thiết lập")
    # API key: ưu tiên st.secrets["GEMINI_API_KEY"]; nếu chưa có, nhập tay
    api_key = st.text_input("GEMINI_API_KEY", value=st.secrets.get("GEMINI_API_KEY", ""), type="password")
    model_name = st.selectbox("Model", ["gemini-1.5-flash", "gemini-1.5-pro"], index=0)
    ref_count = st.number_input("Số tài liệu tham khảo (gợi ý)", min_value=5, max_value=50, value=15)
    language = st.selectbox("Ngôn ngữ đầu ra", ["vi", "en"], index=0)
    st.caption("Khuyên dùng: dùng Secrets trên Streamlit Cloud: Settings → Secrets → GEMINI_API_KEY")

col1, col2 = st.columns([1,2])

with col1:
    st.subheader("1) Nhập tiêu đề")
    title = st.text_input("Tiêu đề bài báo", placeholder="Ví dụ: Tổng quan hệ thống về tăng trưởng xanh tại Việt Nam")
    subtitle = st.text_input("Phụ đề (tuỳ chọn)", placeholder="Bằng chứng giai đoạn 2010–2025")
    keywords = st.text_input("Từ khóa (phân tách bởi dấu phẩy)", value="tăng trưởng xanh, PRISMA, Việt Nam, tổng quan hệ thống")
    review_type = st.selectbox("Loại bài", ["Systematic Review (PRISMA)", "Scoping Review", "Original Research"], index=0)
    btn = st.button("🚀 Dùng Gemini để viết YAML (IMRaD + PRISMA)")

with col2:
    st.subheader("2) YAML sinh ra")
    yaml_area = st.empty()
    st.subheader("3) Kết quả Markdown")
    md_area = st.empty()
    download_md = st.empty()

if btn:
    if not genai:
        st.error("Chưa cài google-generativeai. Hãy thêm vào requirements.txt và deploy lại.")
    elif not api_key:
        st.error("Bạn cần nhập GEMINI_API_KEY (Sidebar).")
    elif not title:
        st.error("Vui lòng nhập tiêu đề.")
    else:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)

            sys_inst = (
                "Bạn là trợ lý biên tập khoa học. Hãy xuất RA DUY NHẤT một YAML hợp lệ cho bài báo theo IMRaD + PRISMA.\n"
                "Trả về các khóa bắt buộc: meta(title, subtitle, date, authors[]), abstract(text, keywords[]), sections("
                "introduction, methods, prisma, results, discussion, conclusion, limitations), acknowledgments, "
                "data_availability, ethics, funding, conflicts_of_interest, references[].\n"
                "references: mỗi mục gồm type (journal_article|book|web_article|conference_paper), authors[family,given], "
                "date (YYYY hoặc YYYY-MM hoặc YYYY-MM-DD), title, container, volume, issue, pages, doi hoặc url.\n"
                "Ngôn ngữ: giữ đúng theo tham số 'language'. Không đưa thêm bình luận ngoài YAML."
            )

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
Trả về YAML hợp lệ, KHÔNG kèm markdown fences.
            """.strip()

            resp = model.generate_content([sys_inst, prompt])
            text = resp.text.strip()

            # parse YAML
            ctx = yaml.safe_load(text) or {}

            # điền meta tối thiểu
            ctx.setdefault("meta", {})
            ctx["meta"]["title"] = ctx["meta"].get("title") or title
            ctx["meta"]["subtitle"] = ctx["meta"].get("subtitle") or subtitle
            ctx["meta"]["date"] = ctx["meta"].get("date") or str(date.today())

            # hiển thị YAML
            yaml_str = yaml.safe_dump(ctx, allow_unicode=True, sort_keys=False)
            yaml_area.code(yaml_str, language="yaml")

            # render Markdown
            tpl = ensure_template()
            md = fill_template(ctx, tpl)
            md_area.markdown(md)

            # download button
            download_md.download_button("⬇️ Tải paper.md", md, file_name="paper.md", mime="text/markdown")

            # lưu tệp tuỳ chọn
            OUTPUT_MD.write_text(md, encoding="utf-8")

            st.success("Đã sinh YAML và Markdown bằng Gemini!")
        except Exception as e:
            st.error(f"Lỗi gọi Gemini hoặc parse YAML: {e}")
            st.stop()

# Hiển thị template để dễ sửa
with st.expander("Xem/tuỳ biến TEMPLATE.md đang dùng"):
    st.code(ensure_template(), language="markdown")
