# streamlit_app_gemini.py (Phiên bản Fix lỗi 404 Model)
import os
import streamlit as st
import google.generativeai as genai

# ================== Cấu hình giao diện ==================
st.set_page_config(page_title="AI Paper Writer (Direct)", layout="wide")
st.title("✍️ AI Scientist: Viết bài báo LaTeX từ chủ đề")

# ================== Sidebar ==================
with st.sidebar:
    st.header("Cấu hình")
    api_key = st.text_input("GEMINI_API_KEY", type="password")
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    # Cập nhật danh sách model để tránh lỗi 404
    model_options = [
        "gemini-1.5-flash",        # Bản nhẹ, nhanh, ít lỗi nhất
        "gemini-1.5-pro",          # Bản mạnh nhất (có thể lỗi nếu acc chưa active)
        "gemini-pro",              # Bản 1.0 ổn định (fallback)
        "gemini-1.5-flash-latest", 
        "gemini-1.5-pro-latest"
    ]
    model_name = st.selectbox("Chọn Model", model_options, index=0)
    
    # Nút kiểm tra xem tài khoản dùng được model nào
    if st.button("🔍 Kiểm tra Model khả dụng"):
        if not api_key:
            st.error("Cần nhập API Key trước.")
        else:
            try:
                genai.configure(api_key=api_key)
                st.info("Đang kết nối lấy danh sách model...")
                available_models = []
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
                st.success(f"Các model hoạt động: {available_models}")
                st.caption("Hãy chọn tên model trong danh sách trên (bỏ chữ 'models/' ở đầu).")
            except Exception as e:
                st.error(f"Lỗi kết nối: {e}")

    language = st.selectbox("Ngôn ngữ bài viết", ["Tiếng Việt", "English"], 0)
    
    st.divider()
    st.markdown("### Thông tin bài báo")
    author_name = st.text_input("Tên tác giả", "Nguyen Van A")
    affiliation = st.text_input("Đơn vị công tác", "University of Technology")
    paper_type = st.selectbox("Loại bài", ["Review Article (Tổng quan)", "Original Research (Nghiên cứu gốc)"])

# ================== Main UI ==================
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Nhập chủ đề")
    topic = st.text_area("Chủ đề bài báo", height=150, 
                        placeholder="Ví dụ: Ứng dụng Blockchain trong quản lý chuỗi cung ứng...")
    extra_instructions = st.text_area("Yêu cầu thêm", placeholder="Ví dụ: 15 tài liệu tham khảo, tập trung vào Việt Nam...")
    generate_btn = st.button("🚀 Viết bài ngay", type="primary")

with col2:
    st.subheader("2. Kết quả (LaTeX Code)")
    latex_output = st.empty()

# ================== Logic xử lý ==================
if generate_btn:
    if not api_key:
        st.error("Vui lòng nhập GEMINI_API_KEY.")
        st.stop()
    if not topic:
        st.warning("Vui lòng nhập chủ đề.")
        st.stop()

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    # Prompt xây dựng bài báo
    if language == "Tiếng Việt":
        sys_prompt = "Bạn là giáo sư, nhà nghiên cứu uy tín. Hãy viết bài báo khoa học chuẩn LaTeX."
        user_req = f"""
        Viết bài báo khoa học về: "{topic}".
        - Tác giả: {author_name} ({affiliation})
        - Loại: {paper_type}
        - Note: {extra_instructions}

        CẤU TRÚC LATEX BẮT BUỘC:
        1. \\documentclass{{article}} (dùng gói 'vietnam' nếu cần).
        2. Title, Abstract.
        3. Sections: Introduction, Methods, Results, Discussion, Conclusion.
        4. References: TỰ TẠO 10-15 trích dẫn giả lập hợp lý, dùng \\cite{{...}} trong bài và liệt kê trong \\begin{{thebibliography}}.

        OUTPUT: Chỉ trả về mã nguồn LaTeX thuần túy (từ \\documentclass đến \\end{{document}}).
        """
    else:
        sys_prompt = "You are a professor. Write a scientific paper in LaTeX."
        user_req = f"""
        Topic: "{topic}".
        - Author: {author_name} ({affiliation})
        - Type: {paper_type}
        - Note: {extra_instructions}

        REQUIRED LATEX STRUCTURE:
        1. \\documentclass{{article}}.
        2. Title, Abstract.
        3. Sections: Introduction, Methods, Results, Discussion, Conclusion.
        4. References: GENERATE 10-15 plausible citations, use \\cite{{...}} in text, list in \\begin{{thebibliography}}.

        OUTPUT: Return ONLY raw LaTeX code.
        """

    with st.spinner(f"Đang dùng model {model_name} để viết..."):
        try:
            response = model.generate_content([sys_prompt, user_req])
            tex_content = response.text
            # Làm sạch code
            tex_content = tex_content.replace("```latex", "").replace("```", "").strip()
            
            latex_output.code(tex_content, language="latex")
            st.download_button("⬇️ Tải file paper.tex", tex_content, "paper.tex", "application/x-tex")
            st.success("Hoàn tất!")
            
        except Exception as e:
            st.error(f"Lỗi API: {e}")
            if "404" in str(e):
                st.warning("Gợi ý: Hãy thử chọn model khác (ví dụ 'gemini-1.5-flash' hoặc 'gemini-pro') ở thanh bên trái.")
