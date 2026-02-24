"""
Shango Revenue Systems — Streamlit Command Center
5-page dashboard: Overview | Pipeline | Calls | Agent Brain | Settings
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client
from datetime import datetime, timedelta
import json

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Shango Revenue Systems — Command Center",
    page_icon="🛰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Dark Theme CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #07070E; }
    .main .block-container { padding: 1.5rem 2rem; }

    .metric-card {
        background: linear-gradient(135deg, #111128 0%, #0D1526 100%);
        border: 1px solid rgba(124, 58, 237, 0.25);
        border-radius: 14px;
        padding: 22px 18px;
        text-align: center;
        margin-bottom: 8px;
    }
    .metric-value {
        font-size: 2.4rem;
        font-weight: 800;
        background: linear-gradient(90deg, #7C3AED, #3B82F6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        line-height: 1.1;
    }
    .metric-delta-pos { color: #10B981; font-size: 0.82rem; margin-top: 4px; }
    .metric-delta-neg { color: #EF4444; font-size: 0.82rem; margin-top: 4px; }
    .metric-label {
        color: #9CA3AF;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        margin-top: 6px;
    }

    .status-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.72rem;
        font-weight: 600;
    }
    .badge-meeting_booked  { background: #065F46; color: #6EE7B7; }
    .badge-follow_up_needed{ background: #92400E; color: #FCD34D; }
    .badge-call_initiated  { background: #1E3A5F; color: #93C5FD; }
    .badge-new             { background: #1F2937; color: #D1D5DB; }
    .badge-nurture_queue   { background: #3B0764; color: #C4B5FD; }
    .badge-closed_lost     { background: #450A0A; color: #FCA5A5; }
    .badge-high  { background: #064E3B; color: #6EE7B7; }
    .badge-medium{ background: #78350F; color: #FCD34D; }
    .badge-low   { background: #1F2937; color: #6B7280; }

    .lead-card {
        padding: 12px 16px;
        margin: 5px 0;
        background: rgba(255,255,255,0.025);
        border-radius: 10px;
        border-left: 3px solid #7C3AED;
    }
    .score-bar { height: 8px; border-radius: 4px; background: #1F2937; overflow: hidden; }
    .score-fill { height: 100%; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)

# ─── Supabase Connection ──────────────────────────────────────────────────────
@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

sb = init_supabase()

# ─── Data Fetchers ────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def fetch_leads():
    r = sb.table("leads").select("*").order("created_at", desc=True).execute()
    df = pd.DataFrame(r.data or [])
    if not df.empty and "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"])
    return df

@st.cache_data(ttl=30)
def fetch_calls():
    r = sb.table("calls").select("*").order("created_at", desc=True).execute()
    df = pd.DataFrame(r.data or [])
    if not df.empty and "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"])
    return df

@st.cache_data(ttl=60)
def fetch_improvements():
    r = sb.table("agent_improvements").select("*").order("created_at", desc=True).limit(30).execute()
    return pd.DataFrame(r.data or [])

@st.cache_data(ttl=60)
def fetch_prompts():
    r = sb.table("prompt_versions").select("*").order("version", desc=True).limit(10).execute()
    return pd.DataFrame(r.data or [])


# ─── Load Data ────────────────────────────────────────────────────────────────
leads_df = fetch_leads()
calls_df = fetch_calls()
improvements_df = fetch_improvements()
prompts_df = fetch_prompts()


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("# 🛰 Shango Revenue Systems")
    st.markdown("**Autonomous AI Sales Agent**")
    st.markdown("---")
    page = st.radio(
        "Navigate",
        ["📊 Overview", "👥 Pipeline", "📞 Call Center", "🧠 Agent Brain", "⚙️ Settings"],
        index=0
    )
    st.markdown("---")

    # Quick KPIs in sidebar
    n = len(leads_df)
    m = len(leads_df[leads_df["status"] == "meeting_booked"]) if not leads_df.empty and "status" in leads_df.columns else 0
    st.metric("Total Leads", n)
    st.metric("Meetings Booked", m)
    if not calls_df.empty and "overall_score" in calls_df.columns:
        av = calls_df["overall_score"].mean()
        st.metric("Avg Call Score", f"{av:.0f}/100")

    st.markdown("---")
    if st.button("♻️ Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 1: OVERVIEW DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
if page == "📊 Overview":
    st.title("🛰 Shango Revenue Systems")
    st.caption("Real-time view of your autonomous AI sales pipeline")

    # ── Top 5 KPIs ─────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)

    total_leads = len(leads_df) if not leads_df.empty else 0
    meetings = len(leads_df[leads_df["status"] == "meeting_booked"]) if not leads_df.empty and "status" in leads_df.columns else 0
    total_calls = len(calls_df) if not calls_df.empty else 0
    avg_score = calls_df["overall_score"].mean() if not calls_df.empty and "overall_score" in calls_df.columns else 0
    conv = (meetings / total_leads * 100) if total_leads > 0 else 0
    total_cost = calls_df["cost_usd"].sum() if not calls_df.empty and "cost_usd" in calls_df.columns else 0

    for col, val, label in [
        (c1, str(total_leads), "Total Leads"),
        (c2, str(total_calls), "Calls Made"),
        (c3, str(meetings), "Meetings Booked"),
        (c4, f"{avg_score:.0f}", "Avg Call Score"),
        (c5, f"{conv:.1f}%", "Conversion Rate"),
    ]:
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{val}</div>
                <div class="metric-label">{label}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── Charts ─────────────────────────────────────────────────────────────
    chart1, chart2 = st.columns(2)

    with chart1:
        st.subheader("Lead Pipeline Status")
        if not leads_df.empty and "status" in leads_df.columns:
            counts = leads_df["status"].value_counts()
            colors = ["#7C3AED","#3B82F6","#10B981","#F59E0B","#EF4444","#6B7280","#8B5CF6"]
            fig = px.pie(
                values=counts.values, names=counts.index,
                color_discrete_sequence=colors, hole=0.45,
            )
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="white", showlegend=True,
                              legend=dict(font=dict(size=10), bgcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No leads yet")

    with chart2:
        st.subheader("Call Scores Over Time")
        if not calls_df.empty and "overall_score" in calls_df.columns:
            sorted_calls = calls_df.sort_values("created_at")
            fig = px.line(sorted_calls, x="created_at", y="overall_score",
                          markers=True, color_discrete_sequence=["#7C3AED"])
            if len(sorted_calls) > 2:
                fig.add_trace(go.Scatter(
                    x=sorted_calls["created_at"],
                    y=sorted_calls["overall_score"].rolling(3).mean(),
                    mode="lines", name="3-Call avg",
                    line=dict(color="#3B82F6", dash="dash"),
                ))
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="white", xaxis_title="Date",
                              yaxis=dict(range=[0, 100], title="Score"))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No calls yet")

    # ── Recent Activity ─────────────────────────────────────────────────────
    st.subheader("🔔 Recent Activity")
    if not leads_df.empty:
        for _, lead in leads_df.head(8).iterrows():
            status = lead.get("status", "new")
            badge = f'<span class="status-badge badge-{status}">{status.replace("_"," ").title()}</span>'
            tier = lead.get("tier", "")
            tier_badge = f'<span class="status-badge badge-{tier}">{tier.upper()}</span>' if tier else ""
            st.markdown(f"""
            <div class="lead-card">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <div>
                        <strong style="color:white">{lead.get("name","?")}</strong>
                        <span style="color:#9CA3AF;margin-left:8px">{lead.get("company","")}</span>
                    </div>
                    <div style="display:flex;gap:8px;align-items:center">
                        <span style="color:#9CA3AF;font-size:0.82rem">Score: {lead.get("score",0)}</span>
                        {tier_badge}
                        {badge}
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("Submit your first lead to see activity here.")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 2: LEAD PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
elif page == "👥 Pipeline":
    st.title("👥 Lead Pipeline")

    if leads_df.empty:
        st.info("No leads yet. Share your landing page to start collecting.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            status_opts = leads_df["status"].unique().tolist() if "status" in leads_df.columns else []
            status_filter = st.multiselect("Status", status_opts, default=status_opts)
        with c2:
            tier_opts = leads_df["tier"].unique().tolist() if "tier" in leads_df.columns else []
            tier_filter = st.multiselect("Tier", tier_opts, default=tier_opts)
        with c3:
            sort = st.selectbox("Sort by", ["created_at", "score", "deal_probability"])

        filtered = leads_df.copy()
        if "status" in filtered.columns and status_filter:
            filtered = filtered[filtered["status"].isin(status_filter)]
        if "tier" in filtered.columns and tier_filter:
            filtered = filtered[filtered["tier"].isin(tier_filter)]
        if sort in filtered.columns:
            filtered = filtered.sort_values(sort, ascending=False)

        st.caption(f"Showing {len(filtered)} of {len(leads_df)} leads")

        for _, lead in filtered.iterrows():
            icon = "🟢" if lead.get("status") == "meeting_booked" else ("🟡" if lead.get("status") == "follow_up_needed" else "🔵")
            with st.expander(f"{icon} {lead.get('name','?')} — {lead.get('company','?')} — Score: {lead.get('score',0)}/100"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"📧 {lead.get('email','N/A')}")
                    st.write(f"📞 {lead.get('phone','N/A')}")
                    st.write(f"🏢 Company: {lead.get('company','N/A')}")
                    st.write(f"📦 Volume: {lead.get('lead_volume','N/A')}")
                with col2:
                    st.write(f"🎯 Tier: **{lead.get('tier','?').upper()}**")
                    st.write(f"💰 Deal probability: {lead.get('deal_probability',0)}%")
                    st.write(f"🛒 Buying stage: {lead.get('buying_stage','unknown')}")
                    st.write(f"📅 Created: {str(lead.get('created_at',''))[:16]}")

                if lead.get("score_reasoning"):
                    st.info(f"💡 AI Reasoning: {lead['score_reasoning']}")

                pains = lead.get("pain_points")
                if pains:
                    if isinstance(pains, str):
                        try: pains = json.loads(pains)
                        except: pass
                    if pains:
                        st.write("**Pain Points:**", ", ".join(pains) if isinstance(pains, list) else str(pains))


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 3: CALL CENTER
# ─────────────────────────────────────────────────────────────────────────────
elif page == "📞 Call Center":
    st.title("📞 Call Center")

    if calls_df.empty:
        st.info("No calls completed yet.")
    else:
        # Score distribution histogram
        st.subheader("Score Distribution")
        if "overall_score" in calls_df.columns:
            fig = px.histogram(calls_df, x="overall_score", nbins=20,
                               color_discrete_sequence=["#7C3AED"], range_x=[0, 100])
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="white", xaxis_title="Score", yaxis_title="Count")
            st.plotly_chart(fig, use_container_width=True)

        # Category scores radar
        cat_cols = ["opening_score","discovery_score","rapport_score",
                    "objection_score","closing_score","naturalness_score","relevance_score"]
        available = [c for c in cat_cols if c in calls_df.columns]
        if available:
            avgs = {c.replace("_score","").replace("_"," ").title(): calls_df[c].mean()
                    for c in available}
            fig2 = go.Figure(go.Scatterpolar(
                r=list(avgs.values()), theta=list(avgs.keys()), fill="toself",
                line_color="#7C3AED", fillcolor="rgba(124,58,237,0.2)",
            ))
            fig2.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100]),
                                          bgcolor="rgba(0,0,0,0)"),
                               paper_bgcolor="rgba(0,0,0,0)", font_color="white",
                               title="Average Category Scores")
            st.plotly_chart(fig2, use_container_width=True)

        # Call log
        st.subheader("Call Log")
        for _, call in calls_df.head(20).iterrows():
            score = call.get("overall_score", 0)
            color = "#10B981" if score >= 70 else ("#F59E0B" if score >= 45 else "#EF4444")
            booked = "✅ Meeting" if call.get("meeting_booked") else ""
            with st.expander(
                f"{'📅' if call.get('meeting_booked') else '📞'} "
                f"Score: {score}/100 {booked} — {str(call.get('created_at',''))[:16]}"
            ):
                st.write(f"**Summary:** {call.get('one_line_summary','N/A')}")
                st.write(f"**Duration:** {call.get('duration_seconds',0)}s")
                st.write(f"**Verdict:** {call.get('full_critique',{}).get('coach_verdict','')}" 
                         if isinstance(call.get('full_critique'), dict) else "")
                if call.get("transcript"):
                    with st.expander("📄 Transcript"):
                        st.text(call["transcript"][:3000])


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 4: AGENT BRAIN
# ─────────────────────────────────────────────────────────────────────────────
elif page == "🧠 Agent Brain":
    st.title("🧠 Agent Brain — Self-Improvement")

    # Current prompt version
    st.subheader("Current Agent Prompt")
    if not prompts_df.empty:
        latest = prompts_df.iloc[0]
        st.success(f"Active: **Version {latest.get('version', '?')}** "
                   f"(based on {latest.get('based_on_calls', 0)} calls)")
        if latest.get("changelog"):
            st.info(f"📝 Changelog: {latest['changelog']}")
        if latest.get("avg_score_before"):
            before = latest.get("avg_score_before", 0)
            after = latest.get("avg_score_after") or "pending"
            st.write(f"Score before: **{before:.1f}** → after: **{after}**")

        with st.expander("📋 View Full Prompt"):
            st.text(latest.get("prompt_text", ""))

        if len(prompts_df) > 1:
            st.subheader("Prompt Version History")
            st.dataframe(
                prompts_df[["version","changelog","based_on_calls",
                             "avg_score_before","avg_score_after","created_at"]].fillna("—"),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.warning("No prompt versions found. Run schema.sql to seed v1.")

    # Pending improvements
    st.markdown("---")
    st.subheader("🔧 Pending Script Improvements")
    if not improvements_df.empty:
        pending = improvements_df[improvements_df.get("status", pd.Series(dtype=str)) == "pending_review"] \
                  if "status" in improvements_df.columns else improvements_df
        st.caption(f"{len(pending)} improvements queued for next update cycle")
        for _, imp in pending.head(15).iterrows():
            impact = imp.get("impact", "medium")
            color = "#EF4444" if impact == "high" else ("#F59E0B" if impact == "medium" else "#6B7280")
            st.markdown(f"""
            <div style="padding:12px;margin:6px 0;background:rgba(255,255,255,0.03);
                        border-radius:8px;border-left:3px solid {color}">
                <strong style="color:{color}">{'🔴' if impact=='high' else '🟡'} {impact.upper()}</strong>
                <span style="color:#9CA3AF;margin-left:8px">{imp.get('improvement_type','')}</span><br>
                <div style="color:#D1D5DB;margin-top:6px">
                    <span style="color:#9CA3AF">Was: </span>{imp.get('current_behavior','')}<br>
                    <span style="color:#10B981">Should be: </span>{imp.get('suggested_behavior','')}<br>
                    <em style="color:#7C3AED">Example: "{imp.get('example_script','')}"</em>
                </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No pending improvements — either no calls yet or all applied.")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 5: SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
elif page == "⚙️ Settings":
    st.title("⚙️ Settings")

    st.subheader("System Configuration")
    st.info("Manage secrets via st.secrets (`.streamlit/secrets.toml`) for security.")

    with st.expander("Required secrets"):
        st.code("""
[secrets]
SUPABASE_URL = "https://xxx.supabase.co"
SUPABASE_KEY = "eyJ..."
BACKEND_URL = "https://your-backend.onrender.com"
""")

    st.markdown("---")
    st.subheader("Manual Controls")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Trigger Improvement Cycle", type="primary", use_container_width=True):
            import requests
            backend = st.secrets.get("BACKEND_URL", "http://localhost:8000")
            try:
                r = requests.post(f"{backend}/webhooks/trigger-improvement",
                                  headers={"X-Admin-Secret": st.secrets.get("ADMIN_SECRET", "")},
                                  timeout=120)
                result = r.json()
                st.success(f"✅ Improvement cycle ran: v{result.get('version')} | {result.get('changelog', '')[:100]}")
            except Exception as e:
                st.error(f"Error: {e}")
    with col2:
        if st.button("🗑️ Clear Cache", use_container_width=True):
            st.cache_data.clear()
            st.success("Cache cleared")

    st.markdown("---")
    st.subheader("Cost Tracker")
    if not calls_df.empty and "cost_usd" in calls_df.columns:
        total = calls_df["cost_usd"].sum()
        today = calls_df[calls_df["created_at"] >= datetime.now().date().isoformat()]["cost_usd"].sum() \
                if "created_at" in calls_df.columns else 0
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Vapi Cost", f"${total:.2f}")
        col2.metric("Today's Cost", f"${today:.2f}")
        col3.metric("Cost per Meeting", f"${total/max(1, len(leads_df[leads_df['status']=='meeting_booked'])) if not leads_df.empty else 0:.2f}")
    else:
        st.info("No call cost data yet.")
