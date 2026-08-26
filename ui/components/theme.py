import streamlit as st


PALETTE = {
    "ink": "#f4f7f6",
    "muted": "#8b9a9d",
    "paper": "#080b0c",
    "panel": "#111718",
    "line": "#263234",
    "teal": "#49d3c8",
    "teal_soft": "#123536",
    "coral": "#ff806d",
    "coral_soft": "#3a211f",
    "gold": "#e6b85c",
    "gold_soft": "#3a2f1a",
    "green": "#70d49a",
}


def inject_theme():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

        :root { --ink:#ffffff; --muted:#ffffff; --paper:#000000; --panel:#000000;
            --line:#242424; --teal:#ffffff; --teal-soft:#111111; --coral:#ffffff;
            --coral-soft:#111111; --gold:#ffffff; --gold-soft:#111111; }
        html, body, [class*="css"] { font-family:'DM Sans', sans-serif; color:#ffffff; }
        h1, h2, h3, h4 { font-family:'Space Grotesk', sans-serif !important; letter-spacing:0 !important; color:var(--ink); }
        .stApp, [data-testid="stAppViewContainer"], main { background:#000000 !important; }
        [data-testid="stHeader"] { background:#000000; }
        [data-testid="stSidebar"], [data-testid="stSidebarContent"] { background:#000000; border-right:0; box-shadow:none !important; }
        section[data-testid="stSidebar"] { box-shadow:none !important; }
        [data-testid="stSidebar"] * { color:#e8f1ef !important; }
        [data-testid="stSidebar"] [data-baseweb="select"] { background:#000000; border-color:#242424; }
        [data-testid="stSidebar"] hr { border-color:#242424; }
        [data-testid="stSidebar"] .stCaption { color:#ffffff !important; }
        .block-container { max-width:1440px; padding:2.4rem 3.5rem 4rem; }
        .eyebrow { color:var(--teal); font-size:.74rem; font-weight:700; letter-spacing:.12em;
                   text-transform:uppercase; margin-bottom:.35rem; }
        .hero { background:#000000; border:1px solid #242424; border-radius:8px; padding:2.2rem 2.5rem; margin-bottom:1.5rem; }
        .hero-centered { background:transparent; border:0; box-shadow:none; text-align:center;
                 padding:5.5rem 1rem 2rem; margin:0 auto; max-width:980px; }
        .hero-centered h1 { font-size:clamp(2.8rem,7vw,6.6rem); line-height:.98; letter-spacing:-.05em !important; }
        .hero h1 { font-size:clamp(2.1rem,4vw,4.2rem); line-height:1.03; margin:.2rem 0 .7rem; }
        .hero p { max-width:720px; color:#ffffff; font-size:1.03rem; line-height:1.65; }
        .dashboard-subtitle { color:#ffffff; line-height:1.6; max-width:720px; }
        .section-label { border-top:1px solid rgba(80,100,98,.35); padding-top:1.1rem; margin-top:2.1rem;
                         color:var(--muted); font-size:.76rem; font-weight:700; letter-spacing:.11em; text-transform:uppercase; }
        div[data-testid="stMetric"] { background:#000000; border:1px solid #242424; border-radius:8px; padding:1rem 1.1rem; }
        div[data-testid="stMetricLabel"] { color:var(--muted); }
        div[data-testid="stMetricValue"] { font-family:'Space Grotesk', sans-serif; }
        .metric-card { min-height:128px; padding:1.1rem 1.2rem; border:1px solid #242424; border-radius:8px; background:#000000; }
        .metric-label { color:#ffffff; font-size:.78rem; text-transform:uppercase; letter-spacing:.1em; }
        .metric-value { color:#ffffff; font-family:'Space Grotesk', sans-serif; font-size:2rem; margin:.45rem 0 .25rem; }
        .metric-delta { color:#ffffff; font-size:.8rem; }
        .metric-delta.positive, .metric-delta.negative, .metric-delta.neutral { color:#ffffff; }
        div[data-testid="stVerticalBlockBorderWrapper"] > div { border-radius:8px; border-color:var(--line); background:var(--panel); }
        .stButton > button { border-radius:5px; font-weight:600; border-color:#333333; background:#000000; color:#ffffff; }
        .stButton > button[kind="primary"] { background:#ffffff; border-color:#ffffff; color:#000000; }
        .stButton > button[kind="primary"] p { color:#000000; }
        input, textarea, [data-baseweb="select"] { background-color:#000000 !important; color:#ffffff !important; border-color:#333333 !important; }
        input[type="radio"], input[type="checkbox"] { accent-color:var(--teal); }
        [data-testid="stInfo"], [data-testid="stWarning"], [data-testid="stError"] { background:#000000; border-color:#333333; color:#ffffff; }
        .stTabs [data-baseweb="tab-list"] { gap:1.4rem; border-bottom:1px solid #242424; }
        .stTabs [data-baseweb="tab"] { padding: .7rem .1rem; color:#ffffff; }
        .stTabs [aria-selected="true"] { border-bottom-color:#ffffff; color:#ffffff; }
        .status-pill { display:inline-block; border-radius:999px; padding:.25rem .65rem; font-size:.72rem;
                       font-weight:700; letter-spacing:.05em; }
        .status-high, .status-medium, .status-low { color:#ffffff; background:#111111; }
        .insight-callout, .action-callout { border-left:4px solid #ffffff; background:#000000; padding:1rem 1.2rem; border-radius:0 8px 8px 0; color:#ffffff; }
        .prompt-box { max-width:760px; margin:1.8rem auto 0; border:1px solid #333333; border-radius:12px;
                  background:#000000; padding:1.15rem 1.3rem; text-align:left; color:#ffffff;
                  box-shadow:0 0 0 5px rgba(73,211,200,.04),0 16px 50px rgba(0,0,0,.3); }
        .prompt-box strong { color:#f4f7f6; font-size:.9rem; }
        .feature-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1.5rem; }
        .feature-card { min-height:150px; padding:1.2rem; border-top:1px solid #242424; }
        .feature-card strong { color:#f4f7f6; }
        .feature-card p { color:#ffffff; line-height:1.55; margin:.5rem 0 0; }
        .stExpander { border-color:#242424 !important; background:#000000; }
        @media (max-width: 800px) { .block-container { padding:1.4rem 1rem 3rem; } .hero { padding:1.5rem; } .feature-grid { grid-template-columns:1fr; gap:.5rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(eyebrow: str, title: str, description: str = ""):
    st.markdown(f'<div class="eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.title(title)
    if description:
        st.markdown(f'<p style="color:#ffffff;max-width:780px;line-height:1.6">{description}</p>', unsafe_allow_html=True)


def section_label(text: str):
    st.markdown(f'<div class="section-label">{text}</div>', unsafe_allow_html=True)
