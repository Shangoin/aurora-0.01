"use client";
import { useState } from "react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

type FormState = "idle" | "loading" | "success" | "error";

const COUNTRY_OPTIONS = [
  { code: "IN",    label: "🇮🇳 India",          prefix: "+91", trust: "📞 Mumbai local call in <5 min" },
  { code: "US",    label: "🇺🇸 United States",   prefix: "+1",  trust: "📞 US number calls you within 5 min" },
  { code: "UK",    label: "🇬🇧 United Kingdom",  prefix: "+44", trust: "📞 UK local call within 5 min" },
  { code: "AU",    label: "🇦🇺 Australia",        prefix: "+61", trust: "📞 International call within 10 min" },
  { code: "SG",    label: "🇸🇬 Singapore",        prefix: "+65", trust: "📞 International call within 10 min" },
  { code: "OTHER", label: "🌍 Other",              prefix: "+",   trust: "📞 International call within 15 min" },
] as const;

type CountryCode = typeof COUNTRY_OPTIONS[number]["code"];

const TIER_ETA: Record<string, string> = {
  high:   "📞 Expect a call in < 5 minutes.",
  medium: "📞 Expect a call within 15 minutes.",
  low:    "📞 Expect a call within 60 minutes.",
};

function detectCountry(): CountryCode {
  if (typeof navigator === "undefined") return "OTHER";
  const lang = navigator.language || "";
  if (lang.startsWith("en-IN") || lang.includes("-IN")) return "IN";
  if (lang.startsWith("en-US") || lang.startsWith("en-CA")) return "US";
  if (lang.startsWith("en-GB")) return "UK";
  if (lang.startsWith("en-AU")) return "AU";
  if (lang.startsWith("zh-SG") || lang.startsWith("en-SG")) return "SG";
  return "OTHER";
}

export default function LandingPage() {
  const [country, setCountry] = useState<CountryCode>(() => detectCountry());
  const [form, setForm] = useState({
    name: "", email: "", phone: "", company: "", lead_volume: "", message: "",
  });
  const [state, setState] = useState<FormState>("idle");
  const [result, setResult] = useState<{ score?: number; tier?: string; message?: string } | null>(null);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setState("loading");
    setError("");

    try {
      const selectedCountry = COUNTRY_OPTIONS.find(c => c.code === country);
      const payload = {
        ...form,
        country_code: selectedCountry?.code || "OTHER",
        phone_prefix: selectedCountry?.prefix || "+",
      };
      const res = await fetch(`${BACKEND_URL}/api/lead`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Submission failed");
      setResult(data);
      setState("success");
    } catch (err: unknown) {
      setError((err as Error).message || "Something went wrong. Please try again.");
      setState("error");
    }
  };

  // ── Success: Score Card ────────────────────────────────────────────────────
  if (state === "success" && result) {
    const score = result.score ?? 0;
    const tier  = (result.tier ?? "").toLowerCase();
    const scoreColor  = getScoreColor(score);
    const tierStyles  = getTierStyle(tier);
    const tierLabel   = tier.toUpperCase();
    const etaLine     = TIER_ETA[tier] ?? (form.phone ? "📞 Expect a call shortly." : "📧 Check your inbox — follow-up coming shortly.");
    // SVG ring
    const R = 54, C = 2 * Math.PI * R;
    const dash = ((score / 100) * C).toFixed(1);

    return (
      <div style={styles.page}>
        <style>{`
          @keyframes spin-in {
            from { stroke-dashoffset: ${C}; }
            to   { stroke-dashoffset: ${C - parseFloat(dash)}; }
          }
          @keyframes pulse-ring {
            0%,100% { opacity: 1; }
            50%      { opacity: 0.6; }
          }
          .score-ring { animation: spin-in 1.2s cubic-bezier(.4,0,.2,1) forwards; }
          ${tier === "high" ? ".tier-badge { animation: pulse-ring 2s ease-in-out infinite; }" : ""}
        `}</style>
        <div style={styles.successPage}>
          <div style={styles.successCard}>
            {/* Score ring */}
            <svg width="140" height="140" style={{ margin: "0 auto 1.5rem", display: "block" }}>
              <circle cx="70" cy="70" r={R} fill="none" stroke="#1F2937" strokeWidth="10" />
              <circle
                className="score-ring"
                cx="70" cy="70" r={R}
                fill="none"
                stroke={scoreColor}
                strokeWidth="10"
                strokeLinecap="round"
                strokeDasharray={`${C}`}
                strokeDashoffset={C}
                transform="rotate(-90 70 70)"
              />
              <text x="70" y="66" textAnchor="middle" fill={scoreColor}
                    fontSize="26" fontWeight="800" fontFamily="-apple-system,sans-serif">
                {score}
              </text>
              <text x="70" y="84" textAnchor="middle" fill="#6B7280"
                    fontSize="11" fontFamily="-apple-system,sans-serif">
                / 100
              </text>
            </svg>

            <h2 style={styles.successTitle}>You're in the pipeline.</h2>

            {/* Tier badge */}
            <div className="tier-badge" style={{ ...styles.tierBadgeWrap, ...tierStyles }}>
              {tier === "high" ? "🔥" : tier === "medium" ? "⚡" : "📋"} {tierLabel} PRIORITY
            </div>

            {/* API message */}
            <p style={styles.successMsg}>{result.message}</p>

            {/* ETA row */}
            <div style={{ ...styles.etaBox, borderColor: scoreColor + "44" }}>
              <span style={{ color: scoreColor, fontSize: "1.1rem" }}>{etaLine}</span>
              {!form.phone && (
                <p style={{ color: "#6B7280", fontSize: "0.78rem", marginTop: 6 }}>
                  No phone provided — email follow-up will be sent instead.
                </p>
              )}
            </div>

            {/* Score bar breakdown */}
            <div style={styles.breakdownRow}>
              {[
                { label: "ICP Fit",  value: score >= 70 ? "Strong" : score >= 45 ? "Moderate" : "Weak", color: scoreColor },
                { label: "Urgency",  value: tier === "high" ? "High" : tier === "medium" ? "Medium" : "Low", color: scoreColor },
                { label: "Lead Score", value: `${score}/100`, color: scoreColor },
              ].map(item => (
                <div key={item.label} style={styles.breakdownItem}>
                  <div style={{ color: "#9CA3AF", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.08em" }}>{item.label}</div>
                  <div style={{ color: item.color, fontWeight: 700, fontSize: "0.95rem", marginTop: 4 }}>{item.value}</div>
                </div>
              ))}
            </div>

            <button style={styles.backBtn} onClick={() => { setState("idle"); setResult(null); }}>
              Submit another lead
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Form ───────────────────────────────────────────────────────────────────
  return (
    <div style={styles.page}>
      {/* Hero */}
      <header style={styles.hero}>
        <nav style={styles.nav}>
          <span style={styles.logo}>🛰 Shango Revenue Systems</span>
          <span style={styles.navTag}>AI Sales Agent</span>
        </nav>
        <h1 style={styles.headline}>
          Stop Losing Leads.<br />
          <span style={styles.gradient}>Let AI Close Them.</span>
        </h1>
        <p style={styles.subheadline}>
          Shango Revenue Systems scores every inbound lead, calls them within 5 minutes, and gets smarter after every call.
          <br />Zero SDRs. Zero missed follow-ups. 10× the output.
        </p>
        <div style={styles.trustRow}>
          {["AI Lead Scoring", "Voice Outreach in 5 min", "Self-Improving Agent", "Full Pipeline Visibility"].map(t => (
            <span key={t} style={styles.trustBadge}>✓ {t}</span>
          ))}
        </div>
      </header>

      {/* Form */}
      <main style={styles.main}>
        <div style={styles.formCard}>
          <h2 style={styles.formTitle}>See Shango Revenue Systems qualify your leads</h2>
          <p style={styles.formSubtitle}>Fill out the form. Our AI will score and call you — live demo in 5 minutes.</p>

          <form onSubmit={handleSubmit} style={styles.form}>
            <div style={styles.row}>
              <div style={styles.field}>
                <label style={styles.label}>Full Name *</label>
                <input
                  style={styles.input}
                  type="text"
                  placeholder="Sarah Chen"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  required
                  minLength={2}
                />
              </div>
              <div style={styles.field}>
                <label style={styles.label}>Work Email *</label>
                <input
                  style={styles.input}
                  type="email"
                  placeholder="sarah@company.com"
                  value={form.email}
                  onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                  required
                />
              </div>
            </div>

            <div style={styles.row}>
              <div style={styles.field}>
                <label style={styles.label}>Country</label>
                <select
                  style={styles.select}
                  value={country}
                  onChange={e => {
                    const next = e.target.value as CountryCode;
                    setCountry(next);
                    const opt = COUNTRY_OPTIONS.find(c => c.code === next);
                    if (opt && !form.phone) {
                      setForm(f => ({ ...f, phone: opt.prefix + " " }));
                    }
                  }}
                >
                  {COUNTRY_OPTIONS.map(opt => (
                    <option key={opt.code} value={opt.code}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div style={styles.field}>
                <label style={styles.label}>Company</label>
                <input
                  style={styles.input}
                  type="text"
                  placeholder="Acme Corp"
                  value={form.company}
                  onChange={e => setForm(f => ({ ...f, company: e.target.value }))}
                />
              </div>
            </div>

            <div style={styles.row}>
              <div style={styles.field}>
                <label style={styles.label}>Phone (for live demo call)</label>
                <input
                  style={styles.input}
                  type="tel"
                  placeholder={COUNTRY_OPTIONS.find(c => c.code === country)?.prefix + " ..."}
                  value={form.phone}
                  onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
                />
                {country !== "OTHER" && (
                  <span style={styles.geoTrust}>
                    {COUNTRY_OPTIONS.find(c => c.code === country)?.trust}
                  </span>
                )}
              </div>
              <div style={styles.field}>
                <label style={styles.label}>Monthly Lead Volume *</label>
                <select
                  style={styles.select}
                  value={form.lead_volume}
                  onChange={e => setForm(f => ({ ...f, lead_volume: e.target.value }))}
                  required
                >
                  <option value="">Select volume...</option>
                  <option value="1-10">1–10 leads/month</option>
                  <option value="10-50">10–50 leads/month</option>
                  <option value="50-200">50–200 leads/month</option>
                  <option value="200+">200+ leads/month</option>
                </select>
              </div>
            </div>

            <div style={styles.field}>
              <label style={styles.label}>What's your biggest sales challenge?</label>
              <textarea
                style={styles.textarea}
                placeholder="e.g. We lose 60% of leads because follow-up is slow and inconsistent..."
                value={form.message}
                onChange={e => setForm(f => ({ ...f, message: e.target.value }))}
                rows={3}
              />
            </div>

            {(state === "error") && <div style={styles.error}>{error}</div>}

            <button
              style={{ ...styles.cta, ...(state === "loading" ? styles.ctaLoading : {}) }}
              type="submit"
              disabled={state === "loading"}
            >
              {state === "loading" ? (
                <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
                  <span style={styles.spinner} />
                  Scoring your lead…
                </span>
              ) : "🚀 Get My AI Call in 5 Minutes"}
            </button>

            <p style={styles.legal}>
              By submitting, you agree to receive an AI-powered demo call. No spam. Unsubscribe anytime.
            </p>
          </form>
        </div>

        {/* How it works */}
        <section style={styles.howItWorks}>
          <h2 style={styles.sectionTitle}>How Shango Revenue Systems Works</h2>
          <div style={styles.steps}>
            {[
              { n: "01", t: "Lead Captured",        d: "Form submits to our API. AI scores lead in under 2 seconds." },
              { n: "02", t: "AI Calls With Local ID",d: "Vapi voice AI calls from a local number — India, US, UK, or Global." },
              { n: "03", t: "9-Dimension Critique",  d: "Claude analyzes the call across 9 dimensions including pacing and silence handling." },
              { n: "04", t: "MARS Self-Improvement", d: "Every 25 calls, MARS + MCTS rewrites the script module-by-module. Smarter every cycle." },
            ].map(s => (
              <div key={s.n} style={styles.step}>
                <div style={styles.stepNum}>{s.n}</div>
                <h3 style={styles.stepTitle}>{s.t}</h3>
                <p style={styles.stepDesc}>{s.d}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer style={styles.footer}>
        <p>© 2026 Shango Revenue Systems — Built on Syntropy tech stack</p>
      </footer>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getScoreColor(score: number): string {
  if (score >= 70) return "#10B981";
  if (score >= 45) return "#F59E0B";
  return "#EF4444";
}

function getTierStyle(tier: string): React.CSSProperties {
  const map: Record<string, React.CSSProperties> = {
    high:   { background: "linear-gradient(135deg,#065F46,#064E3B)", color: "#6EE7B7", border: "1px solid rgba(16,185,129,0.4)" },
    medium: { background: "linear-gradient(135deg,#78350F,#92400E)", color: "#FCD34D", border: "1px solid rgba(245,158,11,0.4)" },
    low:    { background: "linear-gradient(135deg,#1F2937,#111827)", color: "#9CA3AF", border: "1px solid rgba(107,114,128,0.3)" },
  };
  return map[tier] || {};
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  page:         { minHeight: "100vh", background: "#07070E", color: "white", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" },

  // Success score card
  successPage:  { display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", padding: "2rem 1.5rem" },
  successCard:  { width: "100%", maxWidth: 480, background: "linear-gradient(135deg, #111128 0%, #0D1526 100%)", border: "1px solid rgba(124,58,237,0.35)", borderRadius: 24, padding: "2.5rem 2rem", textAlign: "center" },
  successTitle: { fontSize: "1.7rem", fontWeight: 800, marginBottom: "1rem" },
  tierBadgeWrap:{ display: "inline-block", padding: "6px 20px", borderRadius: 9999, fontSize: "0.85rem", fontWeight: 800, letterSpacing: "0.06em", marginBottom: "1.2rem" },
  successMsg:   { color: "#9CA3AF", fontSize: "0.95rem", lineHeight: 1.6, marginBottom: "1.2rem" },
  etaBox:       { background: "rgba(255,255,255,0.03)", border: "1px solid", borderRadius: 12, padding: "14px 18px", marginBottom: "1.5rem" },
  breakdownRow: { display: "flex", justifyContent: "space-around", borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "1.2rem", marginBottom: "1.5rem" },
  breakdownItem:{ display: "flex", flexDirection: "column", alignItems: "center" },
  backBtn:      { background: "rgba(124,58,237,0.15)", border: "1px solid rgba(124,58,237,0.35)", color: "#C4B5FD", borderRadius: 10, padding: "10px 24px", fontSize: "0.88rem", cursor: "pointer" },

  // Hero
  hero:         { maxWidth: 900, margin: "0 auto", padding: "3rem 1.5rem 2rem" },
  nav:          { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "3rem" },
  logo:         { fontSize: "1.4rem", fontWeight: 800, color: "#7C3AED" },
  navTag:       { fontSize: "0.8rem", color: "#6B7280", border: "1px solid #374151", borderRadius: 20, padding: "3px 10px" },
  headline:     { fontSize: "clamp(2.2rem, 5vw, 3.8rem)", fontWeight: 900, lineHeight: 1.1, marginBottom: "1.2rem" },
  gradient:     { background: "linear-gradient(90deg, #7C3AED, #3B82F6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" },
  subheadline:  { fontSize: "clamp(1rem, 2vw, 1.2rem)", color: "#9CA3AF", lineHeight: 1.7, marginBottom: "2rem", maxWidth: 680 },
  trustRow:     { display: "flex", flexWrap: "wrap", gap: 10, marginBottom: "1rem" },
  trustBadge:   { fontSize: "0.8rem", color: "#10B981", border: "1px solid rgba(16,185,129,0.3)", borderRadius: 20, padding: "4px 12px" },

  // Form
  main:         { maxWidth: 900, margin: "0 auto", padding: "0 1.5rem 4rem" },
  formCard:     { background: "linear-gradient(135deg, #111128 0%, #0D1526 100%)", border: "1px solid rgba(124,58,237,0.3)", borderRadius: 20, padding: "2.5rem", marginBottom: "4rem" },
  formTitle:    { fontSize: "1.6rem", fontWeight: 700, marginBottom: 8 },
  formSubtitle: { color: "#9CA3AF", marginBottom: "1.8rem" },
  form:         { display: "flex", flexDirection: "column", gap: 16 },
  row:          { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 },
  field:        { display: "flex", flexDirection: "column", gap: 6 },
  label:        { fontSize: "0.85rem", color: "#D1D5DB", fontWeight: 500 },
  input:        { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, color: "white", padding: "10px 14px", fontSize: "0.95rem", outline: "none" },
  select:       { background: "#111128", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, color: "white", padding: "10px 14px", fontSize: "0.95rem", outline: "none" },
  textarea:     { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, color: "white", padding: "10px 14px", fontSize: "0.95rem", outline: "none", resize: "vertical" },
  cta:          { background: "linear-gradient(135deg, #7C3AED, #3B82F6)", color: "white", border: "none", borderRadius: 12, padding: "14px 28px", fontSize: "1.05rem", fontWeight: 700, cursor: "pointer", marginTop: 8 },
  ctaLoading:   { opacity: 0.7, cursor: "not-allowed" },
  spinner:      { width: 18, height: 18, border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "white", borderRadius: "50%", display: "inline-block", animation: "spin 0.7s linear infinite" } as React.CSSProperties,
  legal:        { color: "#6B7280", fontSize: "0.75rem", textAlign: "center", marginTop: 4 },
  error:        { background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 10, padding: "10px 14px", color: "#FCA5A5", fontSize: "0.9rem" },
  geoTrust:     { fontSize: "0.78rem", color: "#34D399", marginTop: 4 },

  // How it works
  howItWorks:   { padding: "2rem 0" },
  sectionTitle: { fontSize: "1.8rem", fontWeight: 700, marginBottom: "2rem", textAlign: "center" },
  steps:        { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 20 },
  step:         { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 14, padding: "1.5rem" },
  stepNum:      { fontSize: "2rem", fontWeight: 900, color: "#7C3AED", marginBottom: 10 },
  stepTitle:    { fontSize: "1rem", fontWeight: 700, marginBottom: 8 },
  stepDesc:     { color: "#9CA3AF", fontSize: "0.88rem", lineHeight: 1.6 },

  footer:       { textAlign: "center", padding: "2rem", color: "#4B5563", fontSize: "0.85rem", borderTop: "1px solid rgba(255,255,255,0.05)" },
};
