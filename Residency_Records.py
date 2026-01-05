import streamlit as st
import json
import shapefile
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from shapely.prepared import prep
from datetime import datetime, timedelta
import requests, os
import pandas as pd
from io import BytesIO
from zipfile import ZipFile
import plotly.express as px
import streamlit.components.v1 as components


# --- 1. PAGE CONFIG & BACKGROUND ---
st.set_page_config(page_title="TAX RESIDENCY STATUS", layout="wide")

components.html(
    """
    <canvas id="canvas" style="position:fixed; top:0; left:0; width:100vw; height:100vh; z-index:-1; background:#05070A;"></canvas>
    <script>
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    let particles = [];
    function init() {
        canvas.width = window.innerWidth; canvas.height = window.innerHeight;
        particles = [];
        for(let i=0; i<80; i++) {
            particles.push({x: Math.random()*canvas.width, y: Math.random()*canvas.height, vx: (Math.random()-0.5)*0.6, vy: (Math.random()-0.5)*0.6});
        }
    }
    function draw() {
        ctx.clearRect(0,0,canvas.width,canvas.height);
        ctx.fillStyle = 'rgba(96,165,250,0.5)'; ctx.strokeStyle = 'rgba(96,165,250,0.1)';
        particles.forEach((p,i) => {
            p.x+=p.vx; p.y+=p.vy;
            if(p.x<0||p.x>canvas.width) p.vx*=-1; if(p.y<0||p.y>canvas.height) p.vy*=-1;
            ctx.beginPath(); ctx.arc(p.x,p.y,1.5,0,Math.PI*2); ctx.fill();
            for(let j=i+1; j<particles.length; j++) {
                let p2 = particles[j]; let d = Math.hypot(p.x-p2.x, p.y-p2.y);
                if(d<150) { ctx.lineWidth=1-d/150; ctx.beginPath(); ctx.moveTo(p.x,p.y); ctx.lineTo(p2.x,p2.y); ctx.stroke(); }
            }
        });
        requestAnimationFrame(draw);
    }
    window.addEventListener('resize', init); init(); draw();
    </script>
    """, height=0
)

# FORCE DARK MODE
st.markdown("""
    <script>
        var elements = window.parent.document.getElementsByTagName('html')[0];
        elements.setAttribute('data-theme', 'dark');
    </script>
    """, unsafe_allow_html=True)

# --- 2. THEME & TYPOGRAPHY ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600&family=Playfair+Display:wght@700&display=swap');
    
    html, body, [data-testid="stAppViewContainer"], .stText, .stMarkdown p { 
        background: transparent !important; 
        font-family: 'Montserrat', sans-serif !important; 
        color: #E2E8F0 !important; 
    }
    
    h1, h2, h3, h4, .stMetric label {
        font-family: 'Playfair Display', serif !important;
        color: #FFFFFF !important;
        text-align: center !important;
        text-transform: uppercase;
    }

    [data-testid="stSidebar"] { display: none; }
    
    .stMainBlockContainer {
        max-width: 1000px !important;
        margin: auto !important;
        padding-top: 4rem !important;
    }

    .stElementContainer:has(.Residency-anchor) + div [data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(15, 23, 42, 0.75) !important;
        backdrop-filter: blur(15px);
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 28px !important;
        padding: 2.5rem 3rem !important;
        margin: auto !important;
    }

    [data-testid="stMetricValue"] {
        color: #60A5FA !important;
        font-family: 'Montserrat', sans-serif !important;
        font-weight: 600 !important;
        font-size: 2.2rem !important;
    }

    button[data-testid="stBaseButton-secondary"] {
        background-color: rgba(96, 165, 250, 0.1) !important;
        border: 1px solid rgba(96, 165, 250, 0.3) !important;
        color: #60A5FA !important;
        text-transform: uppercase;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. UI LAYOUT ---
st.markdown("<h1 style='text-align:center; margin-bottom:0;'>TAX RESIDENCY STATUS</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#94A3B8; letter-spacing:4px; font-size:0.75rem; margin-bottom:2rem; text-transform:uppercase;'>SUBSTANTIAL PRESENCE TEST (SPT) VERIFICATION</p>", unsafe_allow_html=True)

st.markdown('<div class="Residency-anchor"></div>', unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("<h3>1. DATA CONFIGURATION</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#94A3B8; font-size:0.85rem;'>PLEASE ENSURE YOU UPLOAD ONLY .JSON FILES EXTRACTED FROM GOOGLE.</p>", unsafe_allow_html=True)
    
    files = st.file_uploader("UPLOAD JSON", type=['json'], accept_multiple_files=True, label_visibility="collapsed")
    
    c_info1, c_info2 = st.columns(2)
    with c_info1:
        st.markdown("<h4 style='text-align:center;'>📱 MOBILE CAPTURE</h4>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; font-size:0.9rem;'>MAPS > SETTINGS > PERSONAL CONTENT <br> <b>EXPORT TIMELINE (JSON)</b></p>", unsafe_allow_html=True)
    with c_info2:
        st.markdown("<h4 style='text-align:center;'>💻 CLOUD ARCHIVE</h4>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; font-size:0.9rem;'>VISIT <b>TAKEOUT.GOOGLE.COM</b> <br> TO DOWNLOAD <b>JSON HISTORY</b>.</p>", unsafe_allow_html=True)
    
    st.divider()
    st.markdown("<h3>2. ADJUSTMENTS</h3>", unsafe_allow_html=True)
    adj_col1, adj_col2 = st.columns(2)
    adj_2024 = adj_col1.number_input("2024 DAY CORRECTION", 0, 366, 0)
    adj_2023 = adj_col2.number_input("2023 DAY CORRECTION", 0, 366, 0)

# --- 4. ENGINE ---
@st.cache_resource
def load_us_border():
    dir_name = "us_border_data_strict"
    if not os.path.exists(dir_name):
        url = "https://www2.census.gov/geo/tiger/GENZ2018/shp/cb_2018_us_nation_5m.zip"
        r = requests.get(url)
        with ZipFile(BytesIO(r.content)) as z: z.extractall(dir_name)
    sf = shapefile.Reader(f"{dir_name}/cb_2018_us_nation_5m.shp")
    us_poly = unary_union([shape(s.__geo_interface__) for s in sf.shapes()])
    return prep(us_poly), us_poly.bounds

def extract_data_points(item):
    lat, lon, ts = None, None, item.get('startTime')
    if 'visit' in item:
        loc = item['visit'].get('topCandidate', {}).get('placeLocation', '')
        if 'geo:' in loc:
            parts = loc.replace('geo:', '').split(',')
            if len(parts) == 2: lat, lon = float(parts[0]), float(parts[1])
    elif 'activity' in item:
        loc = item['activity'].get('start', '')
        if 'geo:' in loc:
            parts = loc.replace('geo:', '').split(',')
            if len(parts) == 2: lat, lon = float(parts[0]), float(parts[1])
    return lat, lon, ts

if files:
    prep_poly, bounds = load_us_border()
    minx, miny, maxx, maxy = bounds
    daily_log = {}
    for f in files:
        data = json.load(f)
        items = data if isinstance(data, list) else data.get('timelineObjects', [])
        for item in items:
            lat, lon, ts = extract_data_points(item)
            if lat is None or ts is None: continue
            try:
                date_key = datetime.fromisoformat(ts).strftime('%Y-%m-%d')
            except: continue
            if date_key not in daily_log: daily_log[date_key] = False
            if not daily_log[date_key] and (miny <= lat <= maxy and minx <= lon <= maxx):
                if prep_poly.contains(Point(lon, lat)): daily_log[date_key] = True

    # --- 5. RESULTS ---
    st.markdown("<h3 style='margin-top:2rem;'>3. AUDIT RESULTS</h3>", unsafe_allow_html=True)
    available_years = sorted(list(set([int(d[:4]) for d in daily_log.keys()])))
    audit_year = st.selectbox("CURRENT AUDIT CYCLE", available_years if available_years else [2025], index=len(available_years)-1 if available_years else 0)
    
    d_curr = sum(1 for d, v in daily_log.items() if d.startswith(str(audit_year)) and v)
    d_prev = sum(1 for d, v in daily_log.items() if d.startswith(str(audit_year-1)) and v) + adj_2024
    d_old = sum(1 for d, v in daily_log.items() if d.startswith(str(audit_year-2)) and v) + adj_2023
    score = d_curr + (d_prev / 3) + (d_old / 6)

    if d_curr < 31:
        st.error(f"❌ NON-RESIDENT ALIEN (UNDER 31 DAYS IN {audit_year})")
    elif score >= 183:
        st.success(f"✅ US TAX RESIDENT (WEIGHTED SCORE: {score:.1f})")
    else:
        st.error(f"❌ NON-RESIDENT ALIEN (WEIGHTED SCORE: {score:.1f})")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"{audit_year} DAYS", d_curr)
    m2.metric(f"{audit_year-1} TOTAL", d_prev)
    m3.metric(f"{audit_year-2} TOTAL", d_old)
    m4.metric("SPT SCORE", round(score, 1))


    ledger_df = pd.DataFrame(
        [{"DATE": d, "STATUS": "INSIDE US" if v else "INTERNATIONAL"} 
         for d, v in daily_log.items() if d.startswith(str(audit_year))]
    ).sort_values("DATE")

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        ledger_df.to_excel(writer, index=False, sheet_name='AUDIT_LOG')
        workbook = writer.book
        worksheet = writer.sheets['AUDIT_LOG']

        fmt_base = workbook.add_format({'bg_color': '#0F172A', 'font_color': '#E2E8F0', 'border': 0})
        fmt_header = workbook.add_format({'bg_color': '#1E293B', 'font_color': '#60A5FA', 'bold': True, 'align': 'center', 'bottom': 1, 'bottom_color': '#334155'})
        fmt_us = workbook.add_format({'bg_color': '#0F172A', 'font_color': '#4ADE80'})
        fmt_intl = workbook.add_format({'bg_color': '#0F172A', 'font_color': '#F87171'})

        worksheet.set_column('A:B', 25)
        worksheet.write_row(0, 0, ledger_df.columns, fmt_header)

        for row_num, (index, row) in enumerate(ledger_df.iterrows()):
            status_fmt = fmt_us if row['STATUS'] == "INSIDE US" else fmt_intl
            worksheet.write(row_num + 1, 0, row['DATE'], fmt_base)
            worksheet.write(row_num + 1, 1, row['STATUS'], status_fmt)

    st.download_button(
        label="📥 DOWNLOAD LEDGER (.XLSX)",
        data=buffer.getvalue(),
        file_name=f"residency_ledger_{audit_year}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="secondary"
    )
    # --- 6. CHART ---
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<h3>TRAVEL PATTERN ANALYSIS</h3>", unsafe_allow_html=True)
    chart_year = st.pills("SELECT VIEWING YEAR", options=available_years, default=audit_year)
    
    df_data = [{"Date": d, "Status": "INSIDE US" if v else "INTERNATIONAL"} for d, v in daily_log.items() if d.startswith(str(chart_year))]
    if df_data:
        df = pd.DataFrame(df_data)
        df["Date"] = pd.to_datetime(df["Date"])
        df["Month"] = df["Date"].dt.strftime('%B').str.upper()
        month_order = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]
        
        fig = px.bar(df.groupby(['Month', 'Status']).size().reset_index(name='DAYS'), 
                     x='Month', y='DAYS', color='Status', barmode='stack',
                     template="plotly_dark",
                     category_orders={"Month": month_order},
                     color_discrete_map={"INSIDE US": "#60A5FA", "INTERNATIONAL": "#FFFFFF"})
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(family="Montserrat", color="#E2E8F0"))

        st.plotly_chart(fig, use_container_width=True)

# FOOTER WITH PRIVACY NOTICE
st.markdown("<br><br>", unsafe_allow_html=True)
st.divider()
st.markdown("""
    <div style='text-align: center; color: #94A3B8; font-size: 0.8rem;'>
        <h4>🔒 PRIVACY & DATA SECURITY</h4>
        <p>Your location data is processed locally in memory and is <b>never stored</b> on our servers.<br>
        All data is wiped instantly when you close this browser tab.</p>
    </div>
""", unsafe_allow_html=True)




