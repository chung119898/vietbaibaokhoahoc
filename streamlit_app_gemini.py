# streamlit_app_2026.py (Updated for Gemini 2.5 & 3.0)
import os
import streamlit as st
import google.generativeai as genai

# ================== Cấu hình giao diện ==================
st.set_page_config(page_title="AI Researcher 2026", layout="wide", page_icon="⚡")
st.title("⚡ AI Researcher: Viết báo khoa học (Gemini 2.5 Flash)")
st.caption("Công cụ nghiên cứu sử dụng Google Search Grounding và Model Gemini thế hệ mới nhất (2026).")

# ================== Sidebar ==================
with st.sidebar:
    st.header("Cấu hình Model")
    api_key = st.text_input("GEMINI_API_KEY", type="password")
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    # --- CẬP NHẬT DANH SÁCH MODEL 2026 ---
    model_options = [
        "gemini-2.5-flash",        # [Ổn định] Tốc độ cao, tối ưu chi phí (Release: 06/2025)
        "gemini-3-flash",          # [Mới nhất] Thế hệ 3, thông minh hơn (Release: 12/2025)
        "gemini-2.5-pro",          # [Chuyên sâu] Dành cho tác vụ phức tạp
        "gemini-2.0-flash"         # [Legacy] Bản cũ
    ]
    # Mặc định chọn gemini-2.5-flash như bạn yêu cầu
    model_name = st.selectbox("Chọn Model", model_options, index=0)
    
    language = st.selectbox("Ngôn ngữ", ["Tiếng Việt", "English"], 0)
    
    st.divider()
    st.markdown("### Thông tin bài báo")
    author_name = st.text_input("Tên tác giả", "Nguyen Van A")
    affiliation = st.text_input("Đơn vị công tác", "VNU University of Science")
    paper_type = st.selectbox("Loại bài", ["Original Research", "Review Article", "Short Communication"])

# ================== Main UI ==================
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Nhập chủ đề nghiên cứu")
    topic = st.text_area("Chủ đề", height=150, 
                        placeholder="Ví dụ: Ứng dụng của vật liệu Graphene trong pin xe điện thế hệ mới...")
    extra_instructions = st.text_area("Yêu cầu cụ thể", 
                                     placeholder="Ví dụ: Tập trung vào hiệu suất sạc và độ bền nhiệt. Cần số liệu so sánh thực tế...")
    
    st.info(f"💡 Đang sử dụng model: **{model_name}** với Google Search Grounding.")
    generate_btn = st.button("🚀 Bắt đầu nghiên cứu", type="primary")

with col2:
    st.subheader("2. Kết quả (LaTeX)")
    latex_output = st.empty()
    sources_output = st.container()

# ================== Logic xử lý ==================
if generate_btn:
    if not api_key:
        st.error("Vui lòng nhập GEMINI_API_KEY.")
        st.stop()
    if not topic:
        st.warning("Vui lòng nhập chủ đề.")
        st.stop()

    # Cấu hình API
    genai.configure(api_key=api_key)
    
    # Sử dụng Google Search Retrieval (Grounding)
    tools = 'google_search_retrieval'
    
    try:
        model = genai.GenerativeModel(model_name)
        
        with st.spinner(f"🔍 {model_name} đang tra cứu dữ liệu thực tế..."):
            
            # Prompt được tối ưu cho model 2.5/3.0
            if language == "Tiếng Việt":
                user_req = f"""
                Hãy đóng vai một nhà khoa học dữ liệu. Viết một bài báo khoa học về: "{topic}".
                
                Thông tin tác giả: {author_name} ({affiliation}).
                Loại bài: {paper_type}.
                Ghi chú: {extra_instructions}.

                YÊU CẦU QUAN TRỌNG:
                1. GROUNDING: Bắt buộc sử dụng công cụ tìm kiếm để lấy thông tin, số liệu THỰC TẾ mới nhất (đến năm 2026).
                2. KHÔNG ĐƯỢC BỊA ĐẶT (No Hallucination). Nếu không tìm thấy số liệu, hãy nói rõ.
                3. TRÍCH DẪN: Phần References phải liệt kê các nguồn thực (URL/Paper title) mà bạn đã tìm thấy.

                OUTPUT FORMAT:
                - Trả về RAW LATEX code (bắt đầu từ \\documentclass).
                - Cấu trúc chuẩn: Abstract, Intro, Related Work (Search-based), Methodology, Results (Description), Conclusion, References.
                """
            else:
                user_req = f"""
                Act as a senior researcher. Write a scientific paper on: "{topic}".
                
                Author: {author_name} ({affiliation}).
                Type: {paper_type}.
                Note: {extra_instructions}.

                STRICT REQUIREMENTS:
                1. GROUNDING: You MUST use Google Search to retrieve REAL, up-to-date facts and data (up to 2026).
                2. NO HALLUCINATION: Do not invent data. Use only verified information from search results.
                3. CITATIONS: The References section must list real sources (URLs/Titles) found during the search.

                OUTPUT FORMAT:
                - Return ONLY RAW LATEX code.
                """

            # Gọi API
            response = model.generate_content(user_req, tools=tools)
            
            # Xử lý kết quả
            if response.text:
                tex_content = response.text.replace("```latex", "").replace("```", "").strip()
                latex_output.code(tex_content, language="latex")
                st.download_button("⬇️ Tải file .tex", tex_content, "research_paper.tex", "application/x-tex")
            
            # --- Hiển thị Nguồn (Grounding Metadata) ---
            with sources_output:
                st.divider()
                st.markdown("### 📚 Tài liệu tham khảo & Nguồn dữ liệu")
                
                if response.candidates and response.candidates[0].grounding_metadata:
                    metadata = response.candidates[0].grounding_metadata
                    if metadata.grounding_chunks:
                        st.success("Đã tìm thấy các nguồn dữ liệu thực tế sau:")
                        for i, chunk in enumerate(metadata.grounding_chunks):
                            if chunk.web:
                                st.markdown(f"{i+1}. [{chunk.web.title}]({chunk.web.uri})")
                    else:
                        st.info("Bài viết được tổng hợp từ kiến thức chung (không có link cụ thể).")
                else:
                    st.warning("Lưu ý: Không nhận được metadata nguồn từ API (có thể do cache).")

    except Exception as e:
        st.error(f"Lỗi hệ thống: {e}")
