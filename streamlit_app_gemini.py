# streamlit_app_gemini.py (Updated for Gemini 3.0 - 2026 Edition)
import os
import streamlit as st
import google.generativeai as genai

# ================== Cấu hình giao diện ==================
st.set_page_config(page_title="AI Paper Writer (Gemini 3.0)", layout="wide")
st.title("✍️ AI Scientist: Viết báo khoa học với Gemini 3.0")
st.caption("Sử dụng thế hệ mô hình Gemini 3 mới nhất (2026) cho tốc độ và khả năng tư duy học thuật vượt trội.")

# ================== Sidebar ==================
with st.sidebar:
    st.header("Cấu hình Model")
    api_key = st.text_input("GEMINI_API_KEY", type="password")
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    # CẬP NHẬT DANH SÁCH MODEL MỚI NHẤT (2026)
    model_options = [
        "gemini-3-flash",          # Mới nhất: Tốc độ cực nhanh, mặc định
        "gemini-3-pro",            # Mới nhất: Tư duy sâu (Deep Think)
        "gemini-2.5-flash",        # Bản ổn định trước đó
        "gemini-2.5-pro",          
        "gemini-2.0-flash"         # Legacy
    ]
    model_name = st.selectbox("Chọn Model", model_options, index=0)
    
    # Nút kiểm tra thực tế xem Key của bạn chạy được model nào
    if st.button("🔍 Check Model khả dụng"):
        if not api_key:
            st.error("Cần nhập API Key trước.")
        else:
            try:
                genai.configure(api_key=api_key)
                st.info("Đang kiểm tra API...")
                available_models = []
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        # Chỉ lấy tên ngắn gọn để dễ nhìn
                        name = m.name.replace("models/", "")
                        available_models.append(name)
                st.success(f"Các model Key này dùng được: {available_models}")
            except Exception as e:
                st.error(f"Lỗi kết nối: {e}")

    language = st.selectbox("Ngôn ngữ", ["Tiếng Việt", "English"], 0)
    
    st.divider()
    st.markdown("### Thông tin bài báo")
    author_name = st.text_input("Tên tác giả", "Nguyen Van A")
    affiliation = st.text_input("Đơn vị công tác", "VNU University of Science")
    paper_type = st.selectbox("Loại bài", ["Review Article (Tổng quan)", "Original Research (Nghiên cứu gốc)"])

# ================== Main UI ==================
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Nhập chủ đề")
    topic = st.text_area("Chủ đề bài báo", height=150, 
                        placeholder="Ví dụ: Ứng dụng Generative AI trong giáo dục đại học tại Việt Nam...")
    extra_instructions = st.text_area("Yêu cầu thêm (Tuỳ chọn)", 
                                     placeholder="Ví dụ: Tập trung vào các thách thức đạo đức, trích dẫn chuẩn APA 7...")
    generate_btn = st.button("🚀 Viết bài ngay (Gemini 3.0)", type="primary")

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

    # Prompt tối ưu cho Gemini 3.0 (Tư duy sâu hơn)
    if language == "Tiếng Việt":
        sys_prompt = "Bạn là giáo sư đầu ngành. Hãy viết bài báo khoa học chuẩn LaTeX với tư duy phản biện sắc bén."
        user_req = rf"""
        Viết trọn vẹn một bài báo khoa học về: "{topic}".
        
        THÔNG TIN:
        - Tác giả: {author_name} ({affiliation})
        - Loại bài: {paper_type}
        - Ghi chú: {extra_instructions}

        YÊU CẦU CẤU TRÚC (LaTeX):
        1. \documentclass{{article}} (sử dụng gói 'vietnam', 'geometry', 'cite').
        2. Title, Abstract (Viết súc tích, học thuật).
        3. Các phần: Introduction, Methods, Results, Discussion, Conclusion.
        4. Tài liệu tham khảo: TỰ TỔNG HỢP 15-20 nguồn trích dẫn giả lập nhưng có tính thực tế cao (tên tác giả, năm, tạp chí phù hợp). 
           - Sử dụng lệnh \cite{{key}} trong bài viết.
           - Liệt kê trong môi trường \begin{{thebibliography}}.

        OUTPUT:
        - Chỉ trả về mã nguồn LaTeX (Raw Text).
        - Đảm bảo độ dài và độ sâu chuyên môn phù hợp với Gemini 3.0.
        """
    else:
        sys_prompt = "You are a distinguished professor. Write a high-impact scientific paper in LaTeX."
        user_req = rf"""
        Topic: "{topic}".
        - Author: {author_name} ({affiliation})
        - Type: {paper_type}
        - Note: {extra_instructions}

        REQUIRED LATEX STRUCTURE:
        1. \documentclass{{article}}.
        2. Title, Abstract.
        3. Sections: Introduction, Methods, Results, Discussion, Conclusion.
        4. References: SYNTHESIZE 15-20 high-quality plausible citations. 
           - Use \cite{{key}} throughout the text.
           - List them in \begin{{thebibliography}}.

        OUTPUT: Return ONLY raw LaTeX code.
        """

    with st.spinner(f"Gemini 3.0 ({model_name}) đang suy nghĩ và soạn thảo..."):
        try:
            response = model.generate_content([sys_prompt, user_req])
            tex_content = response.text
            
            # Làm sạch Markdown fences nếu có
            tex_content = tex_content.replace("```latex", "").replace("```", "").strip()
            
            latex_output.code(tex_content, language="latex")
            
            # Tải xuống
            st.download_button(
                label="⬇️ Tải file paper.tex",
                data=tex_content,
                file_name="paper_gemini3.tex",
                mime="application/x-tex"
            )
            st.success(f"Hoàn tất với {model_name}!")
            
        except Exception as e:
            st.error(f"Lỗi: {e}")
            if "404" in str(e) or "not found" in str(e):
                st.warning("Key của bạn có thể chưa hỗ trợ Gemini 3.0. Hãy thử chuyển xuống 'gemini-2.5-flash' ở menu bên trái.")
