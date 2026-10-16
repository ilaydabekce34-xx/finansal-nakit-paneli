# -*- coding: utf-8 -*-
"""
Cash Flow, Runway & KPI Simulator
------------------------------------
Run:  streamlit run app.py
Requirements:  streamlit, pandas, numpy, plotly  (requirements.txt)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Cash Flow & Runway Simulator",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────
CURRENCIES = {"USD": "$", "EUR": "€", "TRY": "₺"}
EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
RUNWAY_CAP = 60  # Max months to simulate for runway

C_POS = "#0E9F8E"      # revenue / positive cash
C_NEG = "#E5484D"      # warning / negative cash
C_EXP = "#F59E0B"      # expense
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
    "Digital Agency (TRY)": dict(
        currency="TRY", cash0=900000.0, mrr=450000.0, growth=3.0,
        fixed=120000.0, variable=90000.0, var_scale=True, payroll=280000.0,
        horizon=12, hire_salary=65000.0,
    ),
    "Profitable SME (EUR)": dict(
        currency="EUR", cash0=60000.0, mrr=40000.0, growth=1.5,
        fixed=8000.0, variable=12000.0, var_scale=True, payroll=15000.0,
        horizon=12, hire_salary=3500.0,
    ),
}

# ──────────────────────────────────────────────────────────────────────────────
# STYLE
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

        .app-title { font-size: 2rem; font-weight: 800; letter-spacing: -0.02em;
                     margin: 0; line-height: 1.15; }
        .app-sub   { opacity: .68; margin: .35rem 0 1.2rem 0; font-size: 1rem; }

        [data-testid="stMetric"] {
            background: rgba(127,127,127,.07);
            border: 1px solid rgba(127,127,127,.22);
            border-radius: 14px;
            padding: 16px 18px;
        }
        [data-testid="stMetricLabel"] p { font-weight: 600; opacity: .75; font-size: .9rem; }
        [data-testid="stMetricValue"]   { font-weight: 800; letter-spacing: -0.02em; }

        [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }

        .sec-title { font-size: 1.15rem; font-weight: 700; margin: 1.6rem 0 .2rem 0; }
        .sec-sub   { opacity: .65; margin-bottom: .6rem; font-size: .92rem; }

        section[data-testid="stSidebar"] .stButton button { width: 100%; }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────
def money(x: float, sym: str, signed: bool = False) -> str:
    body = f"{sym}{abs(x):,.0f}"
    if x < 0:
        return f"-{body}"
    return f"+{body}" if signed and x > 0 else body

def en_num(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}"

def month_label(start: pd.Timestamp, offset: int) -> str:
    d = start + pd.DateOffset(months=offset)
    return f"{EN_MONTHS[d.month - 1]} {d.year}"

def apply_sample(name: str) -> None:
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
# ENGINE
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
    m = np.arange(1, months + 1)
    g = p.growth_pct / 100.0
    uplift = 1 + p.price_up_pct / 100.0
    cut = 1 - p.cost_cut_pct / 100.0

    growth_factor = (1 + g) ** (m - 1)
    revenue = p.mrr * growth_factor * uplift

    fixed = np.full(months, p.fixed * cut)
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
# CHARTS
# ──────────────────────────────────────────────────────────────────────────────
def chart_cash(df, base_df, labels, sym, show_base):
    x = ["Start"] + labels
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
            x=x, y=yb, mode="lines", name="Base scenario",
            line=dict(color=C_BASE, width=2, dash="dash"),
            hovertemplate="%{x}<br>Base: %{y:,.0f}<extra></extra>",
        ))
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines+markers", name="Simulated cash",
        line=dict(color=C_POS, width=3),
        marker=dict(size=7, color=np.where(y < 0, C_NEG, C_POS)),
        hovertemplate="%{x}<br>Cash: " + sym + "%{y:,.0f}<extra></extra>",
    ))

    neg = np.where(y < 0)[0]
    if len(neg):
        i = int(neg[0])
        fig.add_trace(go.Scatter(
            x=[x[i]], y=[y[i]], mode="markers+text", name="Cash depletion",
            marker=dict(size=14, color=C_NEG, symbol="x"),
            text=["Cash out"], textposition="top center",
            textfont=dict(color=C_NEG, size=13),
            hoverinfo="skip",
        ))

    fig.add_hline(y=0, line_dash="dot", line_color=C_NEG, line_width=1.5)
    fig.update_layout(
        height=430, margin=dict(l=10, r=10, t=20, b=10),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis=dict(title=f"Cumulative Cash ({sym})", tickformat=",.0f", zeroline=False),
        xaxis=dict(title=None),
    )
    return fig

def chart_rev_exp(df, labels, sym):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=df["revenue"], name="Revenue",
                         marker_color=C_POS,
                         hovertemplate="%{x}<br>Revenue: " + sym + "%{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Bar(x=labels, y=df["expenses"], name="Expenses",
                         marker_color=C_EXP,
                         hovertemplate="%{x}<br>Expenses: " + sym + "%{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=labels, y=df["net"], name="Net Flow",
                             mode="lines+markers",
                             line=dict(color=C_NEG, width=2.5),
                             marker=dict(size=6),
                             hovertemplate="%{x}<br>Net: " + sym + "%{y:,.0f}<extra></extra>"))
    fig.update_layout(
        barmode="group", height=380, margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis=dict(tickformat=",.0f", title=f"Amount ({sym})"),
        hovermode="x unified",
    )
    return fig

def chart_donut(df, sym):
    vals = [df["fixed"].sum(), df["variable"].sum(), df["payroll"].sum()]
    fig = go.Figure(go.Pie(
        labels=["Fixed Expenses", "Variable Expenses", "Payroll / Salaries"],
        values=vals, hole=0.62, sort=False,
        marker=dict(colors=[C_FIXED, C_VAR, C_PAY]),
        textinfo="percent", textfont=dict(size=14),
        hovertemplate="%{label}<br>" + sym + "%{value:,.0f} (%{percent})<extra></extra>",
    ))
    total = sum(vals)
    fig.add_annotation(text=f"<b>{sym}{total:,.0f}</b><br>total expenses",
                       x=0.5, y=0.5, showarrow=False, font=dict(size=14))
    fig.update_layout(
        height=380, margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", yanchor="top", y=-0.02, x=0),
    )
    return fig

# ──────────────────────────────────────────────────────────────────────────────
# APP
# ──────────────────────────────────────────────────────────────────────────────
inject_css()

if "initialized" not in st.session_state:
    apply_sample("SaaS Startup (USD)")
    st.session_state["sample_choice"] = "SaaS Startup (USD)"
    st.session_state["initialized"] = True

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Parameters")

    st.selectbox("Sample Scenario", list(SAMPLES.keys()), key="sample_choice")
    st.button("Load Sample Scenario", type="primary",
              on_click=lambda: apply_sample(st.session_state["sample_choice"]))

    st.divider()
    st.selectbox(
        "Currency", list(CURRENCIES.keys()), key="currency",
        format_func=lambda c: f"{c} ({CURRENCIES[c]})",
    )
    sym = CURRENCIES[st.session_state["currency"]]

    st.number_input(f"Starting Cash Balance ({sym})", min_value=0.0,
                    step=1000.0, format="%.0f", key="cash0")

    st.markdown("**Revenue**")
    st.number_input(f"Monthly MRR / Sales ({sym})", min_value=0.0,
                    step=500.0, format="%.0f", key="mrr")
    st.slider("Monthly Revenue Growth Rate (%)", -10.0, 30.0, step=0.5, key="growth")

    st.markdown("**Expenses**")
    st.number_input(f"Fixed Expenses - rent, tools, bills ({sym}/mo)",
                    min_value=0.0, step=500.0, format="%.0f", key="fixed")
    st.number_input(f"Variable Expenses - marketing, commissions ({sym}/mo)",
                    min_value=0.0, step=500.0, format="%.0f", key="variable")
    st.checkbox("Scale variable expenses with revenue", key="var_scale",
                help="If checked, variable expenses increase at the same rate as revenue growth.")
    st.number_input(f"Payroll / Salaries ({sym}/mo)", min_value=0.0,
                    step=1000.0, format="%.0f", key="payroll")

    st.divider()
    st.radio("Simulation Horizon (months)", [6, 12, 24], horizontal=True, key="horizon")

# ── MAIN PAGE ─────────────────────────────────────────────────────────────────
st.markdown('<p class="app-title">Cash Flow & Runway Simulator</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="app-sub">See how long your cash will last and test scenarios before making decisions.</p>',
    unsafe_allow_html=True,
)

kpi_area = st.container()

# ── WHAT-IF SIMULATOR ─────────────────────────────────────────────────────────
st.markdown('<p class="sec-title">Scenario Simulator</p>', unsafe_allow_html=True)
st.markdown('<p class="sec-sub">Adjust the sliders; metrics and charts update instantly.</p>',
            unsafe_allow_html=True)

with st.container(border=True):
    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        st.slider("If I increase prices/revenue (%)", 0.0, 100.0, step=1.0, key="price_up",
                  help="Applies a fixed increase to all monthly revenues.")
    with c2:
        st.slider("If I cut expenses (%)", 0.0, 60.0, step=1.0, key="cost_cut",
                  help="Applies to current fixed, variable, and payroll expenses (excluding new hires).")
    with c3:
        st.slider("New hires (people)", 0, 20, step=1, key="hires")
        st.number_input(f"Monthly cost per hire ({sym})", min_value=0.0, step=500.0,
                        format="%.0f", key="hire_salary")
        st.slider("Starting month", 1, 24, key="hire_month",
                  help="New hires will be added to the payroll starting from this month.")
    st.button("Reset Scenario", on_click=reset_whatif)

# ── CALCULATIONS ──────────────────────────────────────────────────────────────
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

# ── KPI CARDS ─────────────────────────────────────────────────────────────────
net1 = float(full_scn.loc[0, "net"])
net1_base = float(full_base.loc[0, "net"])
net_label = "Monthly Net Burn" if net1 < 0 else "Monthly Net Profit"

if runway_scn is None:
    runway_value = f"{RUNWAY_CAP}+ mo"
    date_value = "Sustainable"
    date_help = f"Cash balance does not fall below zero within the next {RUNWAY_CAP} months."
else:
    runway_value = f"{en_num(runway_scn)} mo"
    dep_idx = int(np.floor(runway_scn))
    date_value = month_label(start, dep_idx)
    date_help = "Estimated month when cumulative cash falls below zero."

runway_delta, runway_delta_color = None, "normal"
if whatif_active:
    if runway_scn is not None and runway_base is not None:
        d = runway_scn - runway_base
        if abs(d) >= 0.05:
            runway_delta = f"{'+' if d > 0 else '-'}{en_num(abs(d))} mo (vs base)"
    elif runway_scn is None and runway_base is not None:
        runway_delta, runway_delta_color = "Sustainable vs base", "off"
    elif runway_scn is not None and runway_base is None:
        runway_delta, runway_delta_color = "Worse vs base", "off"

net_delta = None
if whatif_active and abs(net1 - net1_base) >= 0.5:
    net_delta = money(net1 - net1_base, sym, signed=True) + " (vs base)"

with kpi_area:
    if runway_scn is None:
        st.success("Your cash flow looks sustainable: cash does not deplete during the simulation.")
    elif runway_scn < 6:
        st.error(f"Critical: cash runs out in approx. {en_num(runway_scn)} months. "
                 "Try scenarios to increase revenue or cut costs.")
    elif runway_scn < 12:
        st.warning(f"Warning: runway is {en_num(runway_scn)} months. You have time to raise funds "
                   "or grow revenue, but it's limited.")
    else:
        st.success(f"Runway {en_num(runway_scn)} months: You have over 12 months of cash runway.")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Current Cash", money(ss["cash0"], sym),
              help="Starting cash balance.")
    k2.metric(net_label, money(net1, sym), delta=net_delta, delta_color="normal",
              help="Difference between revenue and expenses for the first month.")
    k3.metric("Runway", runway_value,
              delta=runway_delta, delta_color=runway_delta_color,
              help="Time until cash depletion. Revenue growth is factored in.")
    k4.metric("Critical Date", date_value, help=date_help)

    be = breakeven_month(full_scn)
    s1, s2, s3, s4 = st.columns(4)
    s1.metric(f"Total Revenue ({horizon} mo)", money(df["revenue"].sum(), sym))
    s2.metric(f"Total Expenses ({horizon} mo)", money(df["expenses"].sum(), sym))
    s3.metric("Ending Cash", money(float(df["cash"].iloc[-1]), sym))
    s4.metric("Breakeven Month",
              f"Month {be}" if be else "Not reached",
              help="The month when monthly revenue first covers all expenses.")

# ── CHARTS ────────────────────────────────────────────────────────────────────
st.markdown('<p class="sec-title">Cash Projection</p>', unsafe_allow_html=True)
st.markdown('<p class="sec-sub">The red zone indicates when cash falls below zero.</p>',
            unsafe_allow_html=True)
st.plotly_chart(chart_cash(df, base_df, labels, sym, whatif_active),
                use_container_width=True)

col_a, col_b = st.columns([3, 2], gap="large")
with col_a:
    st.markdown('<p class="sec-title">Revenue & Expenses</p>', unsafe_allow_html=True)
    st.plotly_chart(chart_rev_exp(df, labels, sym), use_container_width=True)
with col_b:
    st.markdown('<p class="sec-title">Expense Distribution</p>', unsafe_allow_html=True)
    st.plotly_chart(chart_donut(df, sym), use_container_width=True)

# ── TABLE & CSV ───────────────────────────────────────────────────────────────
st.markdown('<p class="sec-title">Simulation Table</p>', unsafe_allow_html=True)

table = pd.DataFrame({
    "Month Num": df["month"],
    "Period": labels,
    f"Revenue ({sym})": df["revenue"].round(0),
    f"Fixed Exp ({sym})": df["fixed"].round(0),
    f"Variable Exp ({sym})": df["variable"].round(0),
    f"Payroll ({sym})": df["payroll"].round(0),
    f"Total Exp ({sym})": df["expenses"].round(0),
    f"Net Cash Flow ({sym})": df["net"].round(0),
    f"Cumulative Cash ({sym})": df["cash"].round(0),
})

num_cols = [c for c in table.columns if c not in ("Month Num", "Period")]
st.dataframe(
    table.style.format({c: "{:,.0f}" for c in num_cols}),
    use_container_width=True, hide_index=True,
)

csv_bytes = table.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "Download as CSV",
    data=csv_bytes,
    file_name=f"cash_flow_simulation_{horizon}mo.csv",
    mime="text/csv",
    type="primary",
)

st.caption(
    "This tool produces estimated projections; it does not account for taxes, VAT, "
    "collection delays, or seasonality. It does not constitute financial or investment advice."
)
