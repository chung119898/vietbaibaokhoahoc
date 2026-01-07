# streamlit_app_gemini.py (Phiên bản "Viết ngay" - Pure Generation)
import os
import streamlit as st
import google.generativeai as genai

# ================== Cấu hình giao diện ==================
st.set_page_config(page_title="AI Paper Writer (Direct)", layout="wide")
st.title("✍️ AI Scientist: Viết bài báo LaTeX từ chủ đề")
st.caption("Công cụ này dùng Gemini để tự soạn thảo toàn bộ nội dung bài báo (bao gồm cả trích dẫn giả lập/tổng hợp) mà không cần tìm kiếm dữ liệu bên ngoài.")

# ================== Sidebar ==================
with st.sidebar:
    st.header("Cấu hình")
    api_key = st.text_input("GEMINI_API_KEY", type="password")
    # Ưu tiên lấy từ biến môi trường nếu người dùng không nhập
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    model_name = st.selectbox("Chọn Model", ["gemini-1.5-pro", "gemini-1.5-flash"], index=0)
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
    topic = st.text_area("Chủ đề bài báo (Càng chi tiết càng tốt)", height=150, 
                        placeholder="Ví dụ: Ứng dụng Blockchain trong quản lý chuỗi cung ứng nông sản tại Việt Nam...")
    
    extra_instructions = st.text_area("Yêu cầu thêm (Tuỳ chọn)", 
                                     placeholder="Ví dụ: Tập trung vào các thách thức pháp lý, trích dẫn ít nhất 10 nguồn...")
    
    generate_btn = st.button("🚀 Viết bài ngay", type="primary")

with col2:
    st.subheader("2. Kết quả (LaTeX Code)")
    latex_output = st.empty()

# ================== Logic xử lý ==================
if generate_btn:
    if not api_key:
        st.error("Vui lòng nhập GEMINI_API_KEY trong thanh bên trái.")
        st.stop()
    
    if not topic:
        st.warning("Vui lòng nhập chủ đề bài báo.")
        st.stop()

    # Cấu hình Gemini
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    # Tạo Prompt (Câu lệnh)
    if language == "Tiếng Việt":
        sys_prompt = "Bạn là một giáo sư, nhà nghiên cứu khoa học uy tín. Nhiệm vụ của bạn là viết một bài báo khoa học hoàn chỉnh định dạng LaTeX."
        user_req = f"""
        Hãy viết một bài báo khoa học đầy đủ về chủ đề: "{topic}".
        
        THÔNG TIN:
        - Tác giả: {author_name}
        - Đơn vị: {affiliation}
        - Loại bài: {paper_type}
        - Yêu cầu thêm: {extra_instructions}

        CẤU TRÚC BẮT BUỘC (Sử dụng lệnh LaTeX chuẩn):
        1. \\documentclass{{article}} và các gói cần thiết (bao gồm gói tiếng Việt nếu cần).
        2. Tiêu đề, Tác giả, Abstract.
        3. Các phần chính: Giới thiệu (Introduction), Phương pháp (Methods), Kết quả (Results), Thảo luận (Discussion), Kết luận (Conclusion).
        4. Tài liệu tham khảo (References): Hãy TỰ TẠO ra danh sách 10-15 tài liệu tham khảo phù hợp nhất với chủ đề (có thể dựa trên kiến thức đã học hoặc giả lập hợp lý) và dùng lệnh \\cite{{...}} để trích dẫn chúng trong bài. Dùng môi trường \\begin{{thebibliography}}.

        YÊU CẦU ĐẦU RA:
        - Chỉ trả về duy nhất mã nguồn LaTeX (bắt đầu bằng \\documentclass và kết thúc bằng \\end{{document}}).
        - Không trả về Markdown (```latex).
        - Nội dung phải chuyên sâu, văn phong học thuật.
        """
    else:
        sys_prompt = "You are a distinguished professor and scientist. Your task is to write a complete scientific paper in LaTeX format."
        user_req = f"""
        Write a full scientific paper on the topic: "{topic}".
        
        DETAILS:
        - Author: {author_name}
        - Affiliation: {affiliation}
        - Type: {paper_type}
        - Extra instructions: {extra_instructions}

        REQUIRED STRUCTURE (Use standard LaTeX commands):
        1. \\documentclass{{article}} and necessary packages.
        2. Title, Author, Abstract.
        3. Main sections: Introduction, Methods, Results, Discussion, Conclusion.
        4. References: GENERATE 10-15 relevant citations (based on your internal knowledge) and cite them in the text using \\cite{{...}}. Use the \\begin{{thebibliography}} environment.

        OUTPUT REQUIREMENT:
        - Return ONLY raw LaTeX code (starting with \\documentclass and ending with \\end{{document}}).
        - Do not use Markdown fences.
        - Ensure academic tone and depth.
        """

    # Gọi Gemini
    with st.spinner("Gemini đang viết bài... (Quá trình này mất khoảng 30-60 giây)"):
        try:
            response = model.generate_content([sys_prompt, user_req])
            tex_content = response.text
            
            # Làm sạch nếu Gemini lỡ thêm markdown fences
            tex_content = tex_content.replace("```latex", "").replace("```", "").strip()
            
            # Hiển thị kết quả
            latex_output.code(tex_content, language="latex")
            
            # Nút tải xuống
            st.download_button(
                label="⬇️ Tải file paper.tex",
                data=tex_content,
                file_name="paper.tex",
                mime="application/x-tex"
            )
            
            st.success("Đã viết xong! Bạn có thể copy code trên hoặc tải file .tex về để biên dịch.")
            
        except Exception as e:
            st.error(f"Đã xảy ra lỗi: {e}")
