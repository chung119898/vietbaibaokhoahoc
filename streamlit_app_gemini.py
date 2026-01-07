# streamlit_app_gemini.py (Version: Gemini 3.0 + Auto Data Charting)
import os
import json
import re
import streamlit as st
import google.generativeai as genai
import matplotlib.pyplot as plt
import pandas as pd

# ================== Cấu hình giao diện ==================
st.set_page_config(page_title="AI Paper Writer + Chart", layout="wide")
st.title("✍️ AI Scientist: Viết báo & Tự vẽ biểu đồ")
st.caption("Phiên bản nâng cấp: Tự động sinh số liệu giả lập và vẽ biểu đồ minh họa cho bài báo.")

# ================== Sidebar ==================
with st.sidebar:
    st.header("Cấu hình Model")
    api_key = st.text_input("GEMINI_API_KEY", type="password")
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    model_options = [
        "gemini-1.5-flash", 
        "gemini-1.5-pro",
        "gemini-pro"
    ]
    model_name = st.selectbox("Chọn Model", model_options, index=0)
    
    language = st.selectbox("Ngôn ngữ", ["Tiếng Việt", "English"], 0)
    
    st.divider()
    st.markdown("### Thông tin bài báo")
    author_name = st.text_input("Tên tác giả", "Nguyen Van A")
    affiliation = st.text_input("Đơn vị công tác", "VNU University of Science")
    paper_type = st.selectbox("Loại bài", ["Review Article", "Original Research"])
    
    include_chart = st.checkbox("Tự động tạo biểu đồ minh hoạ?", True)

# ================== Helper: Vẽ biểu đồ ==================
def create_chart_from_json(chart_data):
    """
    Vẽ biểu đồ từ JSON và lưu thành file 'chart.png'
    JSON format: {'title': str, 'type': 'bar'|'line', 'x_label': str, 'y_label': str, 'data': [{'label': str, 'value': float}]}
    """
    try:
        data = chart_data.get("data", [])
        if not data: return False
        
        df = pd.DataFrame(data)
        
        fig, ax = plt.subplots(figsize=(8, 5))
        
        # Vẽ tùy loại
        chart_type = chart_data.get("type", "bar")
        if chart_type == "line":
            ax.plot(df['label'], df['value'], marker='o', linestyle='-', color='teal')
        else:
            ax.bar(df['label'], df['value'], color='skyblue')
            
        ax.set_title(chart_data.get("title", "Data Chart"))
        ax.set_xlabel(chart_data.get("x_label", "X"))
        ax.set_ylabel(chart_data.get("y_label", "Y"))
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        # Lưu file để LaTeX dùng
        plt.savefig("chart.png", dpi=300)
        return True
    except Exception as e:
        st.error(f"Lỗi vẽ biểu đồ: {e}")
        return False

# ================== Main UI ==================
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Nhập chủ đề")
    topic = st.text_area("Chủ đề bài báo", height=150, 
                        placeholder="Ví dụ: So sánh hiệu quả của các mô hình Deep Learning trong phân loại ảnh y tế...")
    extra_instructions = st.text_area("Yêu cầu thêm", 
                                     placeholder="Ví dụ: Tập trung vào so sánh CNN và Transformer...")
    generate_btn = st.button("🚀 Viết bài & Vẽ biểu đồ", type="primary")

with col2:
    st.subheader("2. Kết quả")
    chart_area = st.empty()
    latex_output = st.empty()

# ================== Logic xử lý ==================
if generate_btn:
    if not api_key:
        st.error("Thiếu GEMINI_API_KEY.")
        st.stop()
    if not topic:
        st.warning("Vui lòng nhập chủ đề.")
        st.stop()

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    # --- BƯỚC 1: SINH DỮ LIỆU BIỂU ĐỒ (Nếu chọn) ---
    has_chart = False
    chart_desc = ""
    
    if include_chart:
        with st.spinner("Đang sinh số liệu và vẽ biểu đồ..."):
            data_prompt = f"""
            Generate a JSON object for a hypothetical data chart related to the topic: "{topic}".
            It should be realistic data suitable for a scientific paper (e.g., accuracy comparison, growth over years, etc.).
            
            Format (JSON only, no markdown):
            {{
                "title": "Chart Title",
                "type": "bar",  // or "line"
                "x_label": "X Axis Label",
                "y_label": "Y Axis Label",
                "data": [
                    {{"label": "Category A", "value": 85.5}},
                    {{"label": "Category B", "value": 92.1}},
                    ...
                ]
            }}
            """
            try:
                # Dùng model flash cho nhanh
                data_resp = model.generate_content(data_prompt)
                txt = data_resp.text.replace("```json", "").replace("```", "").strip()
                chart_json = json.loads(txt)
                
                # Vẽ
                if create_chart_from_json(chart_json):
                    has_chart = True
                    chart_desc = f"A figure named 'chart.png' (Title: {chart_json['title']}) has been created. Include it in the Results section using \\includegraphics."
                    
                    # Hiển thị lên UI
                    chart_area.image("chart.png", caption=chart_json['title'])
                    st.success("Đã tạo biểu đồ thành công!")
            except Exception as e:
                st.warning(f"Không thể tạo biểu đồ: {e}")

    # --- BƯỚC 2: VIẾT BÀI BÁO ---
    with st.spinner(f"Gemini đang viết bài (kết hợp biểu đồ)..."):
        # Prompt tuỳ chỉnh ngôn ngữ
        chart_instruction = ""
        if has_chart:
            if language == "Tiếng Việt":
                chart_instruction = r"QUAN TRỌNG: Tôi đã có một file ảnh tên là `chart.png` trong thư mục. Hãy chèn nó vào phần 'Kết quả' (Results) bằng lệnh \begin{figure}[h] \centering \includegraphics[width=0.8\textwidth]{chart.png} \caption{...} \label{fig:chart} \end{figure}. Hãy bình luận về số liệu trong biểu đồ này."
            else:
                chart_instruction = r"IMPORTANT: A chart image `chart.png` is available. Insert it into the Results section using \begin{figure}[h] \centering \includegraphics[width=0.8\textwidth]{chart.png} \caption{...} \label{fig:chart} \end{figure}. Discuss the chart data in the text."

        if language == "Tiếng Việt":
            user_req = rf"""
            Viết bài báo khoa học về: "{topic}".
            - Tác giả: {author_name} ({affiliation})
            - Loại: {paper_type}
            - Note: {extra_instructions}
            
            {chart_instruction}

            CẤU TRÚC LATEX:
            1. \documentclass{{article}} (dùng gói vietnam, graphicx).
            2. Title, Abstract.
            3. Sections: Introduction, Methods, Results, Discussion, Conclusion.
            4. References: Tự tạo 10 trích dẫn (\cite{{...}} và \bibitem).

            OUTPUT: Chỉ trả về code LaTeX.
            """
        else:
            user_req = rf"""
            Topic: "{topic}".
            - Author: {author_name} ({affiliation})
            - Type: {paper_type}
            - Note: {extra_instructions}

            {chart_instruction}

            REQUIRED LATEX:
            1. \documentclass{{article}} (use package graphicx).
            2. Title, Abstract.
            3. Sections: Introduction, Methods, Results, Discussion, Conclusion.
            4. References: Generate 10 citations.

            OUTPUT: Return ONLY raw LaTeX code.
            """

        try:
            response = model.generate_content(user_req)
            tex_content = response.text.replace("```latex", "").replace("```", "").strip()
            
            latex_output.code(tex_content, language="latex")
            
            # Download buttons
            st.download_button("⬇️ Tải paper.tex", tex_content, "paper.tex", "application/x-tex")
            if has_chart:
                with open("chart.png", "rb") as f:
                    st.download_button("⬇️ Tải chart.png", f, "chart.png", "image/png")
            
        except Exception as e:
            st.error(f"Lỗi viết bài: {e}")
