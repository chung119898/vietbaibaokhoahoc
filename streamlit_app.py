import streamlit as st
import yaml
from datetime import date
from pathlib import Path

# Dùng lại formatter APA
try:
    from apa_reference_formatter import format_reference
except Exception:
    def format_reference(r):  # fallback rất nhỏ
        return f"{r.get('title','(no title)')}"

TEMPLATE_FILE = Path("TEMPLATE.md")
YAML_FILE = Path("paper.yaml")
OUTPUT_MD = Path("paper.md")

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
    return "\n".join([f"- {format_reference(r)}" for r in (refs or [])])

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

st.set_page_config(page_title="Tạo bài báo khoa học (IMRaD + PRISMA)", layout="wide")
st.title("📝 Trình tạo bài báo khoa học")

# Cột trái: nhập YAML | Cột phải: xem Markdown
col1, col2 = st.columns(2)

# --- Tải sẵn dữ liệu mặc định ---
default_yaml = YAML_FILE.read_text(encoding="utf-8") if YAML_FILE.exists() else """meta:\n  title: \"Tiêu đề\"\nabstract:\n  text: \"Tóm tắt\"\nsections:\n  introduction: \"\""
"""
default_tpl = TEMPLATE_FILE.read_text(encoding="utf-8") if TEMPLATE_FILE.exists() else """# {{TITLE}}\n\n## Tóm tắt\n{{ABSTRACT}}\n\n## 1. Giới thiệu\n{{INTRO}}\n\n## Tài liệu tham khảo\n{{REFERENCES}}"""

with col1:
    st.subheader("1) Nhập/Chỉnh YAML (paper.yaml)")
    yaml_text = st.text_area("Nội dung YAML", value=default_yaml, height=500)
    st.caption("Mẹo: dán `paper.yaml` của bạn vào đây để cập nhật nhanh.")

    uploaded_yaml = st.file_uploader("Hoặc tải file YAML", type=["yaml", "yml"])
    if uploaded_yaml:
        yaml_text = uploaded_yaml.read().decode("utf-8")

    st.subheader("2) Template (TEMPLATE.md)")
    tpl_text = st.text_area("Nội dung Template", value=default_tpl, height=300)

    do_generate = st.button("🚀 Sinh bài báo (Markdown)")

with col2:
    st.subheader("3) Kết quả (paper.md)")
    md_out = ""
    if do_generate:
        try:
            ctx = yaml.safe_load(yaml_text) or {}
            md_out = fill_template(ctx, tpl_text)
            st.success("Đã sinh bài báo thành công!")
        except Exception as e:
            st.error(f"Lỗi YAML/Render: {e}")

    if md_out:
        st.download_button("⬇️ Tải paper.md", md_out, file_name="paper.md", mime="text/markdown")
        st.divider()
        st.markdown(md_out)
    else:
        st.info("Nhấn ‘Sinh bài báo’ để tạo xem trước và tải xuống.")
