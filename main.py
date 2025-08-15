import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import random
import io

# -----------------------------
# Page config & helpers
# -----------------------------
st.set_page_config(
    page_title="Auto Research Writer",
    page_icon="📄",
    layout="wide",
)

STYLE = """
<style>
.reportview-container .markdown-text-container { font-size: 1.05rem; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
h1, h2, h3 { font-weight: 700; }
footer {visibility: hidden;}
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)

# -----------------------------
# Content generation utilities (rule-based, offline)
# -----------------------------

SECTIONS_CORE = [
    ("Abstract", 140, 220),
    ("1. Introduction", 350, 520),
    ("2. Related Work", 280, 420),
    ("3. Methods", 260, 380),
    ("4. Results", 260, 380),
    ("5. Discussion", 260, 380),
    ("6. Conclusion", 150, 240),
]

ARTICLE_TYPES = {
    "Systematic Review": {
        "sections": [
            ("Abstract", 160, 220),
            ("1. Introduction", 350, 520),
            ("2. Methods (Search & Selection)", 260, 380),
            ("3. Results (Bibliometrics/Findings)", 300, 450),
            ("4. Thematic Synthesis", 300, 450),
            ("5. Gaps & Future Directions", 240, 360),
            ("6. Conclusion", 150, 240),
        ],
        "keywords": ["systematic review", "PRISMA", "bibliometric", "trends", "future work"],
    },
    "Empirical Study": {
        "sections": [
            ("Abstract", 160, 220),
            ("1. Introduction", 350, 520),
            ("2. Literature Review", 280, 420),
            ("3. Data & Methods", 260, 380),
            ("4. Results", 260, 380),
            ("5. Robustness & Limitations", 220, 320),
            ("6. Conclusion", 150, 240),
        ],
        "keywords": ["dataset", "methodology", "regression", "validation", "robustness"],
    },
    "Policy Brief": {
        "sections": [
            ("Executive Summary", 140, 200),
            ("1. Background", 250, 360),
            ("2. Problem Statement", 220, 320),
            ("3. Policy Options", 260, 360),
            ("4. Recommendations", 220, 320),
            ("5. Implementation & Monitoring", 220, 320),
            ("6. Conclusion", 120, 200),
        ],
        "keywords": ["policy", "stakeholders", "governance", "implementation", "evaluation"],
    },
}

SENTENCE_TEMPLATES = [
    "{topic} has emerged as a central theme across academia, industry, and policy in the last decade.",
    "Despite rapid progress, open questions remain regarding scalability, equity, and long-term sustainability of {topic}.",
    "We synthesize the state of knowledge on {topic}, identify gaps, and outline actionable directions for future research.",
    "Our analysis balances conceptual clarity with empirical rigor, offering a coherent narrative on {topic}.",
    "Findings suggest that targeted investment, rigorous evaluation, and transparent governance are critical enablers for {topic}.",
    "The implications of {topic} extend to environmental, economic, and social dimensions, requiring cross-disciplinary collaboration.",
]

METHOD_TEMPLATES = [
    "We adopt a transparent protocol, preregistering our plan and adhering to established reporting standards.",
    "Inclusion criteria emphasized relevance to {topic}, methodological rigor, and replicability.",
    "Quantitative synthesis was complemented by qualitative thematic analysis to capture nuance in {topic}.",
    "We performed sensitivity checks and triangulated across data sources to mitigate bias.",
]

RESULT_TEMPLATES = [
    "Across scenarios, we observe consistent improvements associated with targeted interventions in {topic}.",
    "Effect sizes indicate practical significance, though heterogeneity suggests contextual dependencies.",
    "Exploratory analyses reveal non-linearities and potential threshold effects relevant to {topic}.",
]

DISCUSS_TEMPLATES = [
    "The results align with prior work but extend it by formalizing assumptions and testing out-of-sample.",
    "We caution against overgeneralization; external validity depends on data quality and institutional capacity.",
    "Future studies should prioritize open data, preregistered designs, and standardized metrics for {topic}.",
]

CONC_TEMPLATES = [
    "This work provides a concise roadmap for researchers and decision-makers engaging with {topic}.",
    "By integrating methodological transparency with domain expertise, we advance a pragmatic agenda for {topic}.",
]

REF_VENUES = [
    "Nature Sustainability", "Cleaner and Responsible Consumption", "Energy Policy",
    "Journal of Cleaner Production", "PNAS", "Science Advances", "Applied Energy",
]


def _rand_sent(templates, topic, n_range):
    n = random.randint(*n_range)
    picks = random.sample(templates, k=min(n, len(templates)))
    return " ".join(t.format(topic=topic) for t in picks)


def generate_paragraph(topic: str, min_len: int, max_len: int, bank: list) -> str:
    base = _rand_sent(bank, topic, (3, 5))
    # Expand to approximate length with light paraphrases
    extra = []
    while len(" ".join([base] + extra).split()) < random.randint(min_len, max_len):
        extra.append(random.choice(bank).format(topic=topic))
    return " ".join([base] + extra)


def make_title(topic: str, article_type: str) -> str:
    prefixes = {
        "Systematic Review": ["A systematic literature review of", "A bibliometric synthesis of", "Mapping the landscape of"],
        "Empirical Study": ["Evidence on", "Measuring", "Modeling"],
        "Policy Brief": ["Policy pathways for", "A roadmap for", "Governance for"],
    }
    pre = random.choice(prefixes.get(article_type, ["On"]))
    return f"{pre} {topic.lower()}"


def fake_authors() -> str:
    first = ["Alex", "Taylor", "Jordan", "Minh", "Linh", "Aisha", "Diego", "Sara", "Kenji", "Fatima"]
    last = ["Nguyen", "Tran", "Le", "Smith", "Garcia", "Khan", "Zhang", "Kim", "Ivanov", "Rossi"]
    n = random.randint(2, 4)
    names = [f"{random.choice(first)} {random.choice(last)}" for _ in range(n)]
    return ", ".join(names)


def make_keywords(topic: str, extra_hints: list) -> list:
    base = [w.strip() for w in topic.replace("/", ",").split(",") if w.strip()]
    candidates = set(base + extra_hints)
    while len(candidates) < 6:
        candidates.add(random.choice(["sustainability", "metrics", "governance", "innovation", "evaluation", "open science"]))
    return list(candidates)[:6]


def make_references(topic: str, n_refs: int = 12) -> list:
    refs = []
    for _ in range(n_refs):
        year = random.randint(2008, datetime.now().year)
        venue = random.choice(REF_VENUES)
        authors = fake_authors()
        title_bits = ["Impacts of", "Rethinking", "Measuring", "Advances in", "Trends in", "Challenges of"]
        title = f"{random.choice(title_bits)} {topic.lower()}"
        doi_suffix = ''.join(random.choices('0123456789abcdef', k=8))
        refs.append(f"{authors} ({year}). {title}. {venue}. doi:10.1234/{doi_suffix}")
    return refs


def as_markdown(doc):
    out = []
    out.append(f"# {doc['title']}")
    out.append(f"**Authors:** {doc['authors']}")
    out.append(f"**Date:** {doc['date']}")
    out.append(f"**Article type:** {doc['type']}")
    out.append("")
    out.append(f"**Keywords:** {', '.join(doc['keywords'])}")
    out.append("")
    for sec, text in doc['sections']:
        out.append(f"## {sec}")
        out.append(text)
        out.append("")
    if doc.get('table_md'):
        out.append("## Supplementary Table")
        out.append(doc['table_md'])
        out.append("")
    out.append("## References")
    for i, r in enumerate(doc['references'], 1):
        out.append(f"{i}. {r}")
    return "\n".join(out)


def build_article(topic: str, article_type: str, include_fig: bool, include_table: bool):
    meta = ARTICLE_TYPES.get(article_type, {})
    sections = meta.get("sections", SECTIONS_CORE)

    # Compose sections
    section_texts = []
    for sec_name, lo, hi in sections:
        if "Abstract" in sec_name or "Executive Summary" in sec_name:
            bank = SENTENCE_TEMPLATES
        elif "Method" in sec_name or "Data" in sec_name or "Selection" in sec_name:
            bank = METHOD_TEMPLATES
        elif "Result" in sec_name:
            bank = RESULT_TEMPLATES
        elif "Discussion" in sec_name or "Gaps" in sec_name:
            bank = DISCUSS_TEMPLATES
        else:
            bank = SENTENCE_TEMPLATES + DISCUSS_TEMPLATES
        txt = generate_paragraph(topic, lo, hi, bank)
        section_texts.append((sec_name, txt))

    # Metadata
    title = make_title(topic, article_type)
    authors = fake_authors()
    keywords = make_keywords(topic, meta.get("keywords", []))
    references = make_references(topic, n_refs=random.randint(10, 16))

    doc = {
        "title": title.title(),
        "authors": authors,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "type": article_type,
        "keywords": keywords,
        "sections": section_texts,
        "references": references,
    }

    # Optional table
    df = None
    if include_table:
        rng = np.random.default_rng()
        df = pd.DataFrame({
            "Metric": ["Precision", "Recall", "F1", "AUC", "RMSE"],
            "Baseline": rng.uniform(0.6, 0.8, 5).round(3),
            "Proposed": rng.uniform(0.7, 0.92, 5).round(3),
        })
        df["Delta"] = (df["Proposed"] - df["Baseline"]).round(3)
        table_md = df.to_markdown(index=False)
        doc["table_md"] = table_md

    return doc, df


# -----------------------------
# UI
# -----------------------------
st.title("📄 Auto Research Writer")
st.caption("Generate structured, academically-styled articles offline — no external API required.")

col1, col2, col3 = st.columns([2, 1.2, 1])
with col1:
    topic = st.text_input("Topic / Chủ đề", value="Green growth and sustainability")
with col2:
    article_type = st.selectbox("Article type", list(ARTICLE_TYPES.keys()), index=0)
with col3:
    seed = st.number_input("Random seed (optional)", value=0, step=1)

if seed:
    random.seed(int(seed))
    np.random.seed(int(seed))

c1, c2, c3, c4 = st.columns(4)
with c1:
    include_fig = st.checkbox("Add demo chart", value=True)
with c2:
    include_table = st.checkbox("Add demo table", value=True)
with c3:
    show_keywords = st.checkbox("Show keywords", value=True)
with c4:
    n_refs = st.slider("#References", 8, 25, 12)


if st.button("🚀 Generate Article", type="primary"):
    doc, df = build_article(topic.strip(), article_type, include_fig, include_table)
    # Override number of references if user changed slider
    if n_refs:
        doc["references"] = make_references(topic, n_refs)

    # Render header
    st.markdown(f"# {doc['title']}")
    st.markdown(f"**Authors:** {doc['authors']}  ")
    st.markdown(f"**Date:** {doc['date']}  ")
    st.markdown(f"**Article type:** {doc['type']}")
    if show_keywords:
        st.markdown(f"**Keywords:** *{', '.join(doc['keywords'])}*")

    st.divider()

    # Render sections
    for sec, text in doc["sections"]:
        st.subheader(sec)
        st.write(text)

    # Optional figure (synthetic)
    if include_fig:
        st.subheader("Figure 1. Demonstration Time Series")
        x = pd.date_range(datetime.now().date().replace(day=1), periods=36, freq="MS")
        y1 = np.cumsum(np.random.randn(len(x))) + 10
        y2 = y1 + np.random.randn(len(x)) * 0.5 + 2
        fig_df = pd.DataFrame({"Date": x, "Baseline": y1, "Proposed": y2}).set_index("Date")
        st.line_chart(fig_df)
        st.caption("Synthetic data for illustrative purposes only.")

    # Optional table
    if include_table and df is not None:
        st.subheader("Table 1. Performance Summary (Synthetic)")
        st.dataframe(df, use_container_width=True)

    # References
    st.subheader("References")
    for i, r in enumerate(doc["references"], 1):
        st.markdown(f"{i}. {r}")

    # Downloads
    st.divider()
    md = as_markdown(doc)
    st.download_button(
        label="⬇️ Download Markdown",
        data=md,
        file_name=f"{doc['title'].lower().replace(' ', '_')}.md",
        mime="text/markdown",
    )

    # Also offer a simple HTML export for rich copy/paste
    html_buf = io.StringIO()
    html_buf.write(f"<html><head><meta charset='utf-8'><title>{doc['title']}</title></head><body>")
    html_buf.write(md.replace("\n", "<br>"))
    html_buf.write("</body></html>")
    st.download_button(
        label="⬇️ Download Simple HTML",
        data=html_buf.getvalue(),
        file_name=f"{doc['title'].lower().replace(' ', '_')}.html",
        mime="text/html",
    )

    st.success("Done! You can edit the text right in Streamlit or download and refine.")

else:
    st.info("Enter a topic and click **Generate Article** to create a structured draft.")

# Footer
st.caption("Note: This app generates offline, template-based academic prose for drafting and ideation. Always fact-check and edit before submission.")
