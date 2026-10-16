# -*- coding: utf-8 -*-
"""
Nakit Akışı, Runway & KPI Simülatörü
------------------------------------
Çalıştırma:  streamlit run app.py
Gereksinim:  streamlit, pandas, numpy, plotly  (requirements.txt)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# SAYFA AYARLARI
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Nakit Akışı & Runway Simülatörü",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# SABİTLER
# ──────────────────────────────────────────────────────────────────────────────
CURRENCIES = {"USD": "$", "EUR": "€", "TRY": "₺"}
TR_MONTHS = ["Oca", "Şub", "Mar", "Nis", "May", "Haz",
             "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
RUNWAY_CAP = 60  # Runway hesabı için en fazla bu kadar ay ileri simüle edilir

C_POS = "#0E9F8E"      # gelir / pozitif nakit
C_NEG = "#E5484D"      # uyarı / negatif nakit
C_EXP = "#F59E0B"      # gider
C_FIXED = "#6366F1"
C_VAR = "#F59E0B"
C_PAY = "#0EA5E9"
C_BASE = "#94A3B8"

SAMPLES = {
    "SaaS Startup (USD)": dict(
        currency="USD", cash0=250000.0, mrr=18000.0, growth=8.0,
        fixed=6500.0, variable=4000.0, var_scale=True, payroll=32000.0,
        horizon=12, hire_salary=6000.0,
    ),
    "Dijital Ajans (TRY)": dict(
        currency="TRY", cash0=900000.0, mrr=450000.0, growth=3.0,
        fixed=120000.0, variable=90000.0, var_scale=True, payroll=280000.0,
        horizon=12, hire_salary=65000.0,
    ),
    "Kârlı KOBİ (EUR)": dict(
        currency="EUR", cash0=60000.0, mrr=40000.0, growth=1.5,
        fixed=8000.0, variable=12000.0, var_scale=True, payroll=15000.0,
        horizon=12, hire_salary=3500.0,
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# STİL
# ──────────────────────────────────────────────────────────────────────────────
def inject_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"], .stMarkdown, .stMetric, button, input {
            font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif;
        }
        .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1280px; }
        footer, #MainMenu { visibility: hidden; }

        /* Başlık */
        .app-title { font-size: 2rem; font-weight: 800; letter-spacing: -0.02em;
                     margin: 0; line-height: 1.15; }
        .app-sub   { opacity: .68; margin: .35rem 0 1.2rem 0; font-size: 1rem; }

        /* Metrik kartları (açık/koyu tema uyumlu: yarı saydam renkler) */
        [data-testid="stMetric"] {
            background: rgba(127,127,127,.07);
            border: 1px solid rgba(127,127,127,.22);
            border-radius: 14px;
            padding: 16px 18px;
        }
        [data-testid="stMetricLabel"] p { font-weight: 600; opacity: .75; font-size: .9rem; }
        [data-testid="stMetricValue"]   { font-weight: 800; letter-spacing: -0.02em; }

        /* Bordered container'lar */
        [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }

        /* Bölüm başlıkları */
        .sec-title { font-size: 1.15rem; font-weight: 700; margin: 1.6rem 0 .2rem 0; }
        .sec-sub   { opacity: .65; margin-bottom: .6rem; font-size: .92rem; }

        section[data-testid="stSidebar"] .stButton button { width: 100%; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ──────────────────────────────────────────────────────────────────────────────
def money(x: float, sym: str, signed: bool = False) -> str:
    """1234.5 -> $1,235 | negatif -> -$1,235 | signed=True -> +$1,235"""
    body = f"{sym}{abs(x):,.0f}"
    if x < 0:
        return f"-{body}"
    return f"+{body}" if signed and x > 0 else body


def tr_num(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def month_label(start: pd.Timestamp, offset: int) -> str:
    d = start + pd.DateOffset(months=offset)
    return f"{TR_MONTHS[d.month - 1]} {d.year}"


def apply_sample(name: str) -> None:
    """Örnek senaryoyu session_state'e yazar ve what-if kaydırıcılarını sıfırlar."""
    s = SAMPLES[name]
    for k, v in s.items():
        st.session_state[k] = v
    st.session_state["price_up"] = 0.0
    st.session_state["cost_cut"] = 0.0
    st.session_state["hires"] = 0
    st.session_state["hire_month"] = 1


def reset_whatif() -> None:
    st.session_state["price_up"] = 0.0
    st.session_state["cost_cut"] = 0.0
    st.session_state["hires"] = 0
    st.session_state["hire_month"] = 1


# ──────────────────────────────────────────────────────────────────────────────
# HESAPLAMA MOTORU
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Params:
    cash0: float
    mrr: float
    growth_pct: float
    fixed: float
    variable: float
    var_scale: bool
    payroll: float
    price_up_pct: float = 0.0
    cost_cut_pct: float = 0.0
    hires: int = 0
    hire_salary: float = 0.0
    hire_month: int = 1


def simulate(p: Params, months: int = RUNWAY_CAP) -> pd.DataFrame:
    """Aylık nakit akışı simülasyonu. Ay 1 = içinde bulunulan ay."""
    m = np.arange(1, months + 1)
    g = p.growth_pct / 100.0
    uplift = 1 + p.price_up_pct / 100.0
    cut = 1 - p.cost_cut_pct / 100.0

    growth_factor = (1 + g) ** (m - 1)
    revenue = p.mrr * growth_factor * uplift

    fixed = np.full(months, p.fixed * cut)
    # Değişken giderler gelirle birlikte ölçeklenebilir (komisyon, reklam vb.)
    # Fiyat artışı birim maliyeti artırmaz; yalnızca büyüme ölçeği uygulanır.
    var_factor = growth_factor if p.var_scale else np.ones(months)
    variable = p.variable * cut * var_factor

    new_hires_cost = np.where(m >= p.hire_month, p.hires * p.hire_salary, 0.0)
    payroll = p.payroll * cut + new_hires_cost

    total = fixed + variable + payroll
    net = revenue - total
    cash = p.cash0 + np.cumsum(net)

    return pd.DataFrame({
        "month": m,
        "revenue": revenue,
        "fixed": fixed,
        "variable": variable,
        "payroll": payroll,
        "expenses": total,
        "net": net,
        "cash": cash,
    })


def calc_runway(df: pd.DataFrame, cash0: float) -> float | None:
    """Nakdin sıfırın altına indiği ay (kesirli). Düşmüyorsa None."""
    if cash0 <= 0:
        return 0.0
    prev = cash0
    for month, cash in zip(df["month"], df["cash"]):
        if cash < 0:
            return float((month - 1) + prev / (prev - cash))
        prev = cash
    return None


def breakeven_month(df: pd.DataFrame) -> int | None:
    hit = df.index[df["net"] >= 0]
    return int(df.loc[hit[0], "month"]) if len(hit) else None


# ──────────────────────────────────────────────────────────────────────────────
# GRAFİKLER
# ──────────────────────────────────────────────────────────────────────────────
def chart_cash(df, base_df, labels, sym, show_base):
    x = ["Başlangıç"] + labels
    cash0 = float(df.attrs["cash0"])
    y = np.array([cash0] + df["cash"].tolist())

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=np.clip(y, 0, None), mode="lines", line=dict(width=0),
        fill="tozeroy", fillcolor="rgba(14,159,142,0.22)",
        hoverinfo="skip", showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=x, y=np.clip(y, None, 0), mode="lines", line=dict(width=0),
        fill="tozeroy", fillcolor="rgba(229,72,77,0.35)",
        hoverinfo="skip", showlegend=False,
    ))
    if show_base:
        yb = [cash0] + base_df["cash"].tolist()
        fig.add_trace(go.Scatter(
            x=x, y=yb, mode="lines", name="Baz senaryo",
            line=dict(color=C_BASE, width=2, dash="dash"),
            hovertemplate="%{x}<br>Baz: %{y:,.0f}<extra></extra>",
        ))
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines+markers", name="Simüle edilen nakit",
        line=dict(color=C_POS, width=3),
        marker=dict(size=7, color=np.where(y < 0, C_NEG, C_POS)),
        hovertemplate="%{x}<br>Nakit: " + sym + "%{y:,.0f}<extra></extra>",
    ))

    neg = np.where(y < 0)[0]
    if len(neg):
        i = int(neg[0])
        fig.add_trace(go.Scatter(
            x=[x[i]], y=[y[i]], mode="markers+text", name="Nakit biter",
            marker=dict(size=14, color=C_NEG, symbol="x"),
            text=["Nakit biter"], textposition="top center",
            textfont=dict(color=C_NEG, size=13),
            hoverinfo="skip",
        ))

    fig.add_hline(y=0, line_dash="dot", line_color=C_NEG, line_width=1.5)
    fig.update_layout(
        height=430, margin=dict(l=10, r=10, t=20, b=10),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis=dict(title=f"Kümülatif nakit ({sym})", tickformat=",.0f", zeroline=False),
        xaxis=dict(title=None),
    )
    return fig


def chart_rev_exp(df, labels, sym):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=df["revenue"], name="Gelir",
                         marker_color=C_POS,
                         hovertemplate="%{x}<br>Gelir: " + sym + "%{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Bar(x=labels, y=df["expenses"], name="Gider",
                         marker_color=C_EXP,
                         hovertemplate="%{x}<br>Gider: " + sym + "%{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=labels, y=df["net"], name="Net akış",
                             mode="lines+markers",
                             line=dict(color=C_NEG, width=2.5),
                             marker=dict(size=6),
                             hovertemplate="%{x}<br>Net: " + sym + "%{y:,.0f}<extra></extra>"))
    fig.update_layout(
        barmode="group", height=380, margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis=dict(tickformat=",.0f", title=f"Tutar ({sym})"),
        hovermode="x unified",
    )
    return fig


def chart_donut(df, sym):
    vals = [df["fixed"].sum(), df["variable"].sum(), df["payroll"].sum()]
    fig = go.Figure(go.Pie(
        labels=["Sabit giderler", "Değişken giderler", "Personel / maaş"],
        values=vals, hole=0.62, sort=False,
        marker=dict(colors=[C_FIXED, C_VAR, C_PAY]),
        textinfo="percent", textfont=dict(size=14),
        hovertemplate="%{label}<br>" + sym + "%{value:,.0f} (%{percent})<extra></extra>",
    ))
    total = sum(vals)
    fig.add_annotation(text=f"<b>{sym}{total:,.0f}</b><br>toplam gider",
                       x=0.5, y=0.5, showarrow=False, font=dict(size=14))
    fig.update_layout(
        height=380, margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", yanchor="top", y=-0.02, x=0),
    )
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# UYGULAMA
# ──────────────────────────────────────────────────────────────────────────────
inject_css()

# İlk açılışta demo verisiyle başla (boş ekran olmasın)
if "initialized" not in st.session_state:
    apply_sample("SaaS Startup (USD)")
    st.session_state["sample_choice"] = "SaaS Startup (USD)"
    st.session_state["initialized"] = True

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Parametreler")

    st.selectbox("Örnek senaryo", list(SAMPLES.keys()), key="sample_choice")
    st.button("Örnek Senaryoyu Yükle", type="primary",
              on_click=lambda: apply_sample(st.session_state["sample_choice"]))

    st.divider()
    st.selectbox(
        "Para birimi", list(CURRENCIES.keys()), key="currency",
        format_func=lambda c: f"{c} ({CURRENCIES[c]})",
    )
    sym = CURRENCIES[st.session_state["currency"]]

    st.number_input(f"Başlangıç nakit rezervi ({sym})", min_value=0.0,
                    step=1000.0, format="%.0f", key="cash0")

    st.markdown("**Gelir**")
    st.number_input(f"Aylık düzenli gelir – MRR / satış ({sym})", min_value=0.0,
                    step=500.0, format="%.0f", key="mrr")
    st.slider("Aylık gelir büyüme oranı (%)", -10.0, 30.0, step=0.5, key="growth")

    st.markdown("**Giderler**")
    st.number_input(f"Sabit giderler – kira, yazılım, faturalar ({sym}/ay)",
                    min_value=0.0, step=500.0, format="%.0f", key="fixed")
    st.number_input(f"Değişken giderler – pazarlama, komisyon ({sym}/ay)",
                    min_value=0.0, step=500.0, format="%.0f", key="variable")
    st.checkbox("Değişken giderler gelirle birlikte büyüsün", key="var_scale",
                help="Açıkken değişken giderler gelir büyüme oranıyla aynı hızda artar.")
    st.number_input(f"Personel / maaş giderleri ({sym}/ay)", min_value=0.0,
                    step=1000.0, format="%.0f", key="payroll")

    st.divider()
    st.radio("Simülasyon süresi (ay)", [6, 12, 24], horizontal=True, key="horizon")

# ── ANA SAYFA: BAŞLIK ─────────────────────────────────────────────────────────
st.markdown('<p class="app-title">Nakit Akışı & Runway Simülatörü</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="app-sub">Paranızın ne kadar süreceğini görün, kararları vermeden önce '
    'senaryolarla test edin.</p>',
    unsafe_allow_html=True,
)

# KPI alanı: değerler aşağıda hesaplandıktan sonra doldurulacak
kpi_area = st.container()

# ── SENARYO SİMÜLATÖRÜ (What-If) ──────────────────────────────────────────────
st.markdown('<p class="sec-title">Senaryo simülatörü</p>', unsafe_allow_html=True)
st.markdown('<p class="sec-sub">Kaydırıcıları oynatın; kartlar ve grafikler anında güncellenir.</p>',
            unsafe_allow_html=True)

with st.container(border=True):
    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        st.slider("Fiyatları / geliri artırırsam (%)", 0.0, 100.0, step=1.0, key="price_up",
                  help="Tüm aylık gelirlere sabit bir oran uygulanır.")
    with c2:
        st.slider("Giderleri kısarsam (%)", 0.0, 60.0, step=1.0, key="cost_cut",
                  help="Mevcut sabit, değişken ve personel giderlerine uygulanır "
                       "(yeni işe alımlar hariç).")
    with c3:
        st.slider("Yeni işe alım (kişi)", 0, 20, step=1, key="hires")
        st.number_input(f"Kişi başı aylık maliyet ({sym})", min_value=0.0, step=500.0,
                        format="%.0f", key="hire_salary")
        st.slider("İşe başlama ayı", 1, 24, key="hire_month",
                  help="Yeni çalışanlar bu aydan itibaren maaş bordrosuna eklenir.")
    st.button("Senaryoyu sıfırla", on_click=reset_whatif)

# ── HESAPLAMA ─────────────────────────────────────────────────────────────────
ss = st.session_state
horizon = int(ss["horizon"])

base_params = Params(
    cash0=ss["cash0"], mrr=ss["mrr"], growth_pct=ss["growth"],
    fixed=ss["fixed"], variable=ss["variable"], var_scale=ss["var_scale"],
    payroll=ss["payroll"],
)
scn_params = Params(
    cash0=ss["cash0"], mrr=ss["mrr"], growth_pct=ss["growth"],
    fixed=ss["fixed"], variable=ss["variable"], var_scale=ss["var_scale"],
    payroll=ss["payroll"],
    price_up_pct=ss["price_up"], cost_cut_pct=ss["cost_cut"],
    hires=int(ss["hires"]), hire_salary=ss["hire_salary"], hire_month=int(ss["hire_month"]),
)
whatif_active = (ss["price_up"] > 0 or ss["cost_cut"] > 0 or ss["hires"] > 0)

full_scn = simulate(scn_params, RUNWAY_CAP)
full_base = simulate(base_params, RUNWAY_CAP)

runway_scn = calc_runway(full_scn, ss["cash0"])
runway_base = calc_runway(full_base, ss["cash0"])

df = full_scn.head(horizon).copy()
df.attrs["cash0"] = ss["cash0"]
base_df = full_base.head(horizon).copy()

start = pd.Timestamp.today().normalize().replace(day=1)
labels = [month_label(start, i) for i in range(horizon)]

# ── KPI KARTLARI ──────────────────────────────────────────────────────────────
net1 = float(full_scn.loc[0, "net"])
net1_base = float(full_base.loc[0, "net"])
net_label = "Aylık Net Yakım" if net1 < 0 else "Aylık Net Kazanç"

if runway_scn is None:
    runway_value = f"{RUNWAY_CAP}+ ay"
    date_value = "Sürdürülebilir"
    date_help = f"Önümüzdeki {RUNWAY_CAP} ay içinde nakit sıfırın altına düşmüyor."
else:
    runway_value = f"{tr_num(runway_scn)} ay"
    dep_idx = int(np.floor(runway_scn))
    date_value = month_label(start, dep_idx)
    date_help = "Kümülatif nakdin sıfırın altına düşeceği tahmini ay."

runway_delta, runway_delta_color = None, "normal"
if whatif_active:
    if runway_scn is not None and runway_base is not None:
        d = runway_scn - runway_base
        if abs(d) >= 0.05:
            runway_delta = f"{'+' if d > 0 else '-'}{tr_num(abs(d))} ay (baza göre)"
    elif runway_scn is None and runway_base is not None:
        runway_delta, runway_delta_color = "Baz senaryoya göre sürdürülebilir", "off"
    elif runway_scn is not None and runway_base is None:
        runway_delta, runway_delta_color = "Baz senaryoya göre kötüleşti", "off"

net_delta = None
if whatif_active and abs(net1 - net1_base) >= 0.5:
    net_delta = money(net1 - net1_base, sym, signed=True) + " (baza göre)"

with kpi_area:
    # Durum bandı
    if runway_scn is None:
        st.success("Nakit akışınız sürdürülebilir görünüyor: simülasyon boyunca kasa sıfıra inmiyor.")
    elif runway_scn < 6:
        st.error(f"Kritik: nakit yaklaşık {tr_num(runway_scn)} ay içinde bitiyor. "
                 "Gelir artırma veya gider kısma senaryolarını deneyin.")
    elif runway_scn < 12:
        st.warning(f"Dikkat: runway {tr_num(runway_scn)} ay. Yatırım veya gelir artışı için "
                   "zaman var, ancak sınırlı.")
    else:
        st.success(f"Runway {tr_num(runway_scn)} ay: 12 aydan uzun bir nakit ömrünüz var.")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Mevcut Kasa", money(ss["cash0"], sym),
              help="Başlangıç nakit bakiyesi.")
    k2.metric(net_label, money(net1, sym), delta=net_delta, delta_color="normal",
              help="İlk ayın gelir – gider farkı (senaryo etkileri dahil).")
    k3.metric("Kalan Yaşam Süresi (Runway)", runway_value,
              delta=runway_delta, delta_color=runway_delta_color,
              help="Nakdin tükenmesine kalan süre. Gelir büyümesi hesaba katılır.")
    k4.metric("Kritik Eşik Tarihi", date_value, help=date_help)

    be = breakeven_month(full_scn)
    s1, s2, s3, s4 = st.columns(4)
    s1.metric(f"Toplam Gelir ({horizon} ay)", money(df["revenue"].sum(), sym))
    s2.metric(f"Toplam Gider ({horizon} ay)", money(df["expenses"].sum(), sym))
    s3.metric("Dönem Sonu Nakit", money(float(df["cash"].iloc[-1]), sym))
    s4.metric("Başa Baş Noktası",
              f"{be}. ay" if be else "Ulaşılamıyor",
              help="Aylık gelirin giderleri ilk kez karşıladığı ay.")

# ── GRAFİKLER ─────────────────────────────────────────────────────────────────
st.markdown('<p class="sec-title">Nakit projeksiyonu</p>', unsafe_allow_html=True)
st.markdown('<p class="sec-sub">Kırmızı bölge nakdin negatife düştüğü dönemi gösterir.</p>',
            unsafe_allow_html=True)
st.plotly_chart(chart_cash(df, base_df, labels, sym, whatif_active),
                use_container_width=True)

col_a, col_b = st.columns([3, 2], gap="large")
with col_a:
    st.markdown('<p class="sec-title">Gelir ve gider</p>', unsafe_allow_html=True)
    st.plotly_chart(chart_rev_exp(df, labels, sym), use_container_width=True)
with col_b:
    st.markdown('<p class="sec-title">Gider dağılımı</p>', unsafe_allow_html=True)
    st.plotly_chart(chart_donut(df, sym), use_container_width=True)

# ── TABLO & CSV ───────────────────────────────────────────────────────────────
st.markdown('<p class="sec-title">Simülasyon tablosu</p>', unsafe_allow_html=True)

table = pd.DataFrame({
    "Ay": df["month"],
    "Dönem": labels,
    f"Gelir ({sym})": df["revenue"].round(0),
    f"Sabit Gider ({sym})": df["fixed"].round(0),
    f"Değişken Gider ({sym})": df["variable"].round(0),
    f"Personel Gideri ({sym})": df["payroll"].round(0),
    f"Toplam Gider ({sym})": df["expenses"].round(0),
    f"Net Nakit Akışı ({sym})": df["net"].round(0),
    f"Kümülatif Nakit ({sym})": df["cash"].round(0),
})

num_cols = [c for c in table.columns if c not in ("Ay", "Dönem")]
st.dataframe(
    table.style.format({c: "{:,.0f}" for c in num_cols}),
    use_container_width=True, hide_index=True,
)

csv_bytes = table.to_csv(index=False).encode("utf-8-sig")  # Excel'de Türkçe karakter uyumu
st.download_button(
    "CSV Olarak İndir",
    data=csv_bytes,
    file_name=f"nakit_akisi_simulasyonu_{horizon}ay.csv",
    mime="text/csv",
    type="primary",
)

st.caption(
    "Bu araç tahmini projeksiyonlar üretir; vergi, KDV, tahsilat gecikmesi ve mevsimsellik "
    "hesaba katılmaz. Yatırım veya finansal tavsiye niteliği taşımaz."
)
