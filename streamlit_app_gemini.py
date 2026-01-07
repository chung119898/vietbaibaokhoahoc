# streamlit_app_gemini.py (Fix lỗi Model + Giữ tính năng Vẽ biểu đồ)
import os
import json
import streamlit as st
import google.generativeai as genai
import matplotlib.pyplot as plt
import pandas as pd

# ================== Cấu hình giao diện ==================
st.set_page_config(page_title="AI Paper Writer + Chart", layout="wide")
st.title("✍️ AI Scientist: Viết báo & Tự vẽ biểu đồ")
st.caption("Sử dụng Gemini 1.5 để tự động sinh số liệu, vẽ biểu đồ và viết bài báo khoa học.")

# ================== Sidebar ==================
with st.sidebar:
    st.header("Cấu hình Model")
    api_key = st.text_input("GEMINI_API_KEY", type="password")
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    # SỬA LẠI DANH SÁCH MODEL CHUẨN ĐANG HOẠT ĐỘNG
    model_options = [
        "gemini-1.5-flash",        # Bản nhanh, ổn định nhất hiện nay
        "gemini-1.5-pro",          # Bản mạnh về tư duy
        "gemini-pro"               # Bản 1.0 (Legacy)
    ]
    model_name = st.selectbox("Chọn Model", model_options, index=0)
    
    # Nút kiểm tra nhanh
    if st.button("🔍 Kiểm tra kết nối"):
        if not api_key:
            st.error("Chưa nhập API Key")
        else:
            try:
                genai.configure(api_key=api_key)
                genai.list_models()
                st.success("Kết nối API thành công!")
            except Exception as e:
                st.error(f"Lỗi Key: {e}")

    language = st.selectbox("Ngôn ngữ", ["Tiếng Việt", "English"], 0)
    
    st.divider()
    st.markdown("### Thông tin bài báo")
    author_name = st.text_input("Tên tác giả", "Nguyen Van A")
    affiliation = st.text_input("Đơn vị công tác", "VNU University of Science")
    paper_type = st.selectbox("Loại bài", ["Review Article", "Original Research"])
    
    # TÙY CHỌN: Tự động vẽ biểu đồ
    include_chart = st.checkbox("Tự động tạo biểu đồ minh hoạ?", True)

# ================== Helper: Vẽ biểu đồ từ JSON ==================
def create_chart_from_json(chart_data):
    """
    Vẽ biểu đồ từ JSON và lưu thành file 'chart.png'
    """
    try:
        data = chart_data.get("data", [])
        if not data: return False
        
        df = pd.DataFrame(data)
        
        # Cấu hình style
        plt.figure(figsize=(8, 5))
        
        # Vẽ tùy loại
        chart_type = chart_data.get("type", "bar")
        colors = ['#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F']
        
        if chart_type == "line":
            plt.plot(df['label'], df['value'], marker='o', linestyle='-', color='#4E79A7', linewidth=2)
            plt.grid(True, linestyle='--', alpha=0.5)
        else:
            plt.bar(df['label'], df['value'], color=colors[:len(df)])
            
        plt.title(chart_data.get("title", "Data Chart"), fontsize=14, fontweight='bold')
        plt.xlabel(chart_data.get("x_label", "X"), fontsize=11)
        plt.ylabel(chart_data.get("y_label", "Y"), fontsize=11)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        # Lưu file để LaTeX dùng
        plt.savefig("chart.png", dpi=300)
        plt.close() # Đóng plot để giải phóng mem
        return True
    except Exception as e:
        st.error(f"Lỗi vẽ biểu đồ: {e}")
        return False

# ================== Main UI ==================
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Nhập chủ đề")
    topic = st.text_area("Chủ đề bài báo", height=150, 
                        placeholder="Ví dụ: Hiệu quả của mô hình AI trong chẩn đoán ung thư phổi...")
    extra_instructions = st.text_area("Yêu cầu thêm", 
                                     placeholder="Ví dụ: So sánh độ chính xác (Accuracy) giữa các thuật toán...")
    generate_btn = st.button("🚀 Viết bài & Vẽ hình", type="primary")

with col2:
    st.subheader("2. Kết quả")
    chart_area = st.empty()
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

    # --- BƯỚC 1: SINH DỮ LIỆU & VẼ BIỂU ĐỒ (Nếu chọn) ---
    has_chart = False
    
    if include_chart:
        with st.spinner("🤖 Đang phân tích chủ đề và sinh số liệu giả lập..."):
            # Prompt chuyên biệt để sinh JSON dữ liệu
            data_prompt = f"""
            Generate a JSON object for a HYPOTHETICAL data chart related to the topic: "{topic}".
            The data should be realistic and suitable for a scientific paper.
            
            STRICT JSON FORMAT (No markdown):
            {{
                "title": "Chart Title (Scientific)",
                "type": "bar",  // OR "line"
                "x_label": "X Axis Label",
                "y_label": "Y Axis Label",
                "data": [
                    {{"label": "Item A", "value": 85.5}},
                    {{"label": "Item B", "value": 92.1}},
                    ... (min 4 items)
                ]
            }}
            """
            try:
                # Gọi model
                data_resp = model.generate_content(data_prompt)
                txt = data_resp.text.replace("```json", "").replace("```", "").strip()
                
                # Xử lý trường hợp Gemini trả về text thừa
                start_idx = txt.find("{")
                end_idx = txt.rfind("}") + 1
                if start_idx != -1 and end_idx != -1:
                    json_str = txt[start_idx:end_idx]
                    chart_json = json.loads(json_str)
                    
                    # Vẽ biểu đồ bằng Matplotlib
                    if create_chart_from_json(chart_json):
                        has_chart = True
                        chart_area.image("chart.png", caption=f"Hình 1: {chart_json['title']}")
                        st.success("✅ Đã tạo biểu đồ dữ liệu thành công!")
                else:
                    st.warning("Không tìm thấy JSON hợp lệ trong phản hồi dữ liệu.")
                    
            except Exception as e:
                st.warning(f"Không thể tạo biểu đồ (Lỗi: {e}). Tiếp tục viết bài không có hình.")

    # --- BƯỚC 2: VIẾT BÀI BÁO LATEX ---
    with st.spinner(f"✍️ Gemini đang viết bài báo ({model_name})..."):
        
        # Hướng dẫn chèn ảnh nếu có
        chart_instruction = ""
        if has_chart:
            if language == "Tiếng Việt":
                chart_instruction = r"""
                QUAN TRỌNG: Tôi đã có sẵn một file ảnh tên là `chart.png`. 
                Hãy chèn nó vào phần 'Kết quả' (Results) bằng lệnh LaTeX: 
                \begin{figure}[h] \centering \includegraphics[width=0.8\textwidth]{chart.png} \caption{Mô tả biểu đồ...} \label{fig:chart1} \end{figure}
                Và hãy viết một đoạn văn bình luận/phân tích về số liệu trong biểu đồ này.
                """
            else:
                chart_instruction = r"""
                IMPORTANT: A chart image named `chart.png` is available. 
                Insert it into the 'Results' section using:
                \begin{figure}[h] \centering \includegraphics[width=0.8\textwidth]{chart.png} \caption{Chart description...} \label{fig:chart1} \end{figure}
                And write a paragraph analyzing the data shown in this chart.
                """

        # Prompt chính
        if language == "Tiếng Việt":
            user_req = rf"""
            Viết bài báo khoa học về: "{topic}".
            - Tác giả: {author_name} ({affiliation})
            - Loại: {paper_type}
            - Note: {extra_instructions}
            
            {chart_instruction}

            CẤU TRÚC LATEX BẮT BUỘC:
            1. \documentclass{{article}} (dùng gói 'vietnam', 'graphicx', 'geometry', 'cite').
            2. Title, Abstract.
            3. Sections: Introduction, Methods, Results, Discussion, Conclusion.
            4. References: TỰ TẠO 15 tài liệu tham khảo giả lập nhưng hợp lý.
            
            OUTPUT: Chỉ trả về mã nguồn LaTeX (Raw Text).
            """
        else:
            user_req = rf"""
            Topic: "{topic}".
            - Author: {author_name} ({affiliation})
            - Type: {paper_type}
            - Note: {extra_instructions}

            {chart_instruction}

            REQUIRED LATEX:
            1. \documentclass{{article}} (use package 'graphicx').
            2. Title, Abstract.
            3. Sections: Introduction, Methods, Results, Discussion, Conclusion.
            4. References: Generate 15 plausible citations.

            OUTPUT: Return ONLY raw LaTeX code.
            """

        try:
            response = model.generate_content(user_req)
            tex_content = response.text.replace("```latex", "").replace("```", "").strip()
            
            latex_output.code(tex_content, language="latex")
            
            # Nút tải xuống
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.download_button("⬇️ Tải paper.tex", tex_content, "paper.tex", "application/x-tex")
            if has_chart:
                with col_d2:
                    with open("chart.png", "rb") as f:
                        st.download_button("⬇️ Tải chart.png", f, "chart.png", "image/png")
            
        except Exception as e:
            st.error(f"Lỗi viết bài: {e}")
