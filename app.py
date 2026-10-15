import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import revops_lib as L

st.set_page_config(page_title="Ringostat RevOps Dashboard", layout="wide")

ACCENT = "#3a86b8"      # one hue for all magnitude bars; readable on light and dark backgrounds
MUTED = "#8b98a5"       # low-sample / neutral bars
LOST = "#d9825b"
GRID = "rgba(128,128,128,0.25)"   # neutral grid, visible on both themes
# Text colour is intentionally NOT set: Plotly inherits it from the Streamlit theme (light or dark).


@st.cache_data
def get_data() -> pd.DataFrame:
    return L.load()


def style(fig: go.Figure, height: int = 340, pct: bool = False) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(size=13),
        bargap=0.35,
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickformat=".0%" if pct else None)
    return fig


def winrate_bar(g: pd.DataFrame, cat: str, min_n: int, horizontal: bool = False) -> go.Figure:
    g = g.copy()
    colors = [ACCENT if n >= min_n else MUTED for n in g["closed"]]
    labels = [f"{w:.0%}  (n={n})" for w, n in zip(g["win_rate"], g["closed"])]
    hover = [f"{c}<br>Win rate: {w:.1%}<br>Won {won} of {n} closed" for c, w, won, n in zip(g[cat], g["win_rate"], g["won"], g["closed"])]
    if horizontal:
        fig = go.Figure(go.Bar(y=g[cat], x=g["win_rate"], orientation="h", marker_color=colors, text=labels,
                               textposition="outside", cliponaxis=False, hovertext=hover, hoverinfo="text"))
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(range=[0, min(1.0, max(g["win_rate"].max() * 1.35, 0.1))], tickformat=".0%")
        style(fig, height=max(260, 34 * len(g) + 40))
        fig.update_xaxes(showgrid=True, gridcolor=GRID)
        fig.update_yaxes(showgrid=False)
    else:
        fig = go.Figure(go.Bar(x=g[cat], y=g["win_rate"], marker_color=colors, text=labels, textposition="outside",
                               cliponaxis=False, hovertext=hover, hoverinfo="text"))
        fig.update_yaxes(range=[0, min(1.0, max(g["win_rate"].max() * 1.25, 0.1))])
        style(fig, pct=True)
    return fig


df = get_data()

# ------------------------------------------------------------------ sidebar filters
st.sidebar.header("Filters")
countries = sorted(df["Client country"].unique(), key=lambda c: -(df["Client country"] == c).sum())
sel_countries = st.sidebar.multiselect("Client country", countries, default=[], placeholder="All countries")
crms = sorted(df["crm"].unique(), key=lambda c: -(df["crm"] == c).sum())
sel_crms = st.sidebar.multiselect("Client CRM", crms, default=[], placeholder="All CRMs")
dmin, dmax = df["aql_date"].min().date(), df["aql_date"].max().date()
date_range = st.sidebar.date_input("AQL date range", value=(dmin, dmax), min_value=dmin, max_value=dmax)
min_n = st.sidebar.slider("Min. closed deals for a solid bar", 5, 50, 15,
                          help="Bars with fewer closed deals are greyed out: their win rate is statistically noisy.")
st.sidebar.caption("Win rate = Closed Won / (Closed Won + Closed Lost). Open deals are excluded because their outcome is unknown.")

f = df.copy()
if sel_countries:
    f = f[f["Client country"].isin(sel_countries)]
if sel_crms:
    f = f[f["crm"].isin(sel_crms)]
if isinstance(date_range, tuple) and len(date_range) == 2:
    f = f[(f["aql_date"].dt.date >= date_range[0]) & (f["aql_date"].dt.date <= date_range[1])]

st.title("Ringostat: RevOps dashboard")
tab_dash, tab_issues = st.tabs(["Dashboard", "Data issues"])

with tab_dash:
    closed = f[f["is_closed"]]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Deals (filtered)", f"{len(f):,}")
    c2.metric("Closed deals", f"{len(closed):,}")
    c3.metric("Win rate", f"{closed['is_won'].mean():.1%}" if len(closed) else "n/a")
    c4.metric("Still open", f"{(~f['is_closed']).sum():,}")
    if f.empty:
        st.warning("No deals match the filters.")
        st.stop()

    left, right = st.columns(2)
    with left:
        st.subheader("Win rate by country")
        g = L.win_rate(f, "country_code")
        big = g[g["closed"] >= min_n]
        small = g[g["closed"] < min_n]
        if len(small):
            other = pd.DataFrame([{"country_code": f"Other ({len(small)} countries)", "won": small["won"].sum(),
                                   "closed": small["closed"].sum()}])
            other["win_rate"] = other["won"] / other["closed"]
            big = pd.concat([big, other], ignore_index=True)
        big = big.sort_values("closed", ascending=False)
        if len(big):
            st.plotly_chart(winrate_bar(big, "country_code", min_n), width="stretch")
        st.caption(f"Countries with fewer than {min_n} closed deals are grouped into 'Other'.")
    with right:
        st.subheader("Win rate by CRM")
        g = L.win_rate(f, "crm")
        big = g[g["closed"] >= min_n].sort_values("win_rate", ascending=False)
        small = g[g["closed"] < min_n]
        if len(big):
            st.plotly_chart(winrate_bar(big, "crm", min_n, horizontal=True), width="stretch")
        st.caption(f"{len(small)} CRMs with fewer than {min_n} closed deals are hidden (total {int(small['closed'].sum())} deals).")

    left, right = st.columns(2)
    with left:
        st.subheader("Deals by stage")
        s = f["Stage"].value_counts().reindex(L.STAGE_ORDER).fillna(0).astype(int).reset_index()
        s.columns = ["Stage", "Deals"]
        fig = go.Figure(go.Bar(x=s["Stage"], y=s["Deals"], marker_color=ACCENT, text=s["Deals"], textposition="outside",
                               cliponaxis=False, hovertemplate="%{x}: %{y} deals<extra></extra>"))
        fig.update_yaxes(range=[0, s["Deals"].max() * 1.15 or 1])
        st.plotly_chart(style(fig), width="stretch")
    with right:
        st.subheader("Deals by source")
        s = f["Source"].value_counts().reset_index()
        s.columns = ["Source", "Deals"]
        fig = go.Figure(go.Bar(y=s["Source"], x=s["Deals"], orientation="h", marker_color=ACCENT, text=s["Deals"],
                               textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x} deals<extra></extra>"))
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(range=[0, s["Deals"].max() * 1.15])
        style(fig, height=max(300, 30 * len(s) + 40))
        fig.update_xaxes(showgrid=True, gridcolor=GRID)
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(fig, width="stretch")

    st.subheader("Trend by AQL month")
    m = f.assign(month=f["aql_date"].dt.to_period("M"))
    mg = m.groupby("month").agg(deals=("Stage", "size"), won=("is_won", "sum"), closed=("is_closed", "sum")).reset_index()
    mg["lost"] = mg["closed"] - mg["won"]
    mg["open"] = mg["deals"] - mg["closed"]
    mg["win_rate"] = mg["won"] / mg["closed"].where(mg["closed"] > 0)
    last = df["aql_date"].max()
    mg["label"] = [p.strftime("%b %Y") + (" *" if p.end_time.normalize() > last else "") for p in mg["month"]]
    left, right = st.columns(2)
    with left:
        st.caption("Deals by outcome")
        fig = go.Figure()
        for name, col, colr in [("Closed Won", "won", ACCENT), ("Closed Lost", "lost", LOST), ("Open", "open", MUTED)]:
            fig.add_bar(x=mg["label"], y=mg[col], name=name, marker_color=colr, text=[str(v) if v >= 25 else "" for v in mg[col]], textposition="inside", textangle=0,
                        hovertemplate="%{x}: %{y} " + name + "<extra></extra>")
        fig.update_layout(barmode="stack")
        style(fig)
        fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.12, x=0))
        st.plotly_chart(fig, width="stretch")
    with right:
        st.caption("Win rate (closed deals only)")
        wm = mg[mg["closed"] > 0].copy()
        wm[["won", "closed"]] = wm[["won", "closed"]].astype(int)
        st.plotly_chart(winrate_bar(wm, "label", min_n), width="stretch")
    st.caption("\\* Partial month at the edge of the data. Recent months are not comparable with older ones: "
               "many of their deals are still open (see the Open share in the left chart), so their win rate can still change.")

    st.subheader("Win rate vs PPC budget")
    g = L.win_rate(f, "PPC budget USD").set_index("PPC budget USD").reindex(L.PPC_ORDER).dropna().reset_index()
    g[["won", "closed"]] = g[["won", "closed"]].astype(int)
    if len(g):
        st.plotly_chart(winrate_bar(g, "PPC budget USD", min_n), width="stretch")
    st.caption("PPC budget is a range bucket in the source data, so it is shown as ordered categories, not a scatter. "
               "Ranges are not equal in size and the sample per bucket varies a lot (see n); grey bars are below the sample threshold. "
               "The bucket 10000-20000 does not exist in the data.")

with tab_issues:
    summary, rows = L.data_issues(df)
    st.markdown("Checks run on the **full dataset** (filters do not apply). Row numbers match the source sheet.")
    st.caption("Severity: **High** - the record contradicts its own Stage, so win rate, stage counts or cycle time are distorted. "
               "**Medium** - breaks a field rule or may inflate the deal count (cannot be confirmed without a deal ID). "
               "**Low** - suspicious but possibly legitimate value, or a labelling inconsistency; no effect on core metrics.")
    st.dataframe(summary, hide_index=True, width="stretch", height=(len(summary) + 1) * 35 + 3)
    st.subheader("Data issues: affected rows")
    sev = st.multiselect("Severity", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
    chk = st.multiselect("Check", summary.loc[summary["Rows"] > 0, "Check"].tolist(), placeholder="All checks")
    view = rows[rows["Severity"].isin(sev)] if len(rows) else rows
    if chk:
        view = view[view["Check"].isin(chk)]
    st.dataframe(view, hide_index=True, width="stretch")
    st.download_button("Download data issues (CSV)", view.to_csv(index=False).encode("utf-8"), "data_issues.csv", "text/csv")
