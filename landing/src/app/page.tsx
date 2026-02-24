"use client";
import { useState } from "react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

type FormState = "idle" | "loading" | "success" | "error";

export default function LandingPage() {
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
      const res = await fetch(`${BACKEND_URL}/api/lead`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Submission failed");
      setResult(data);
      setState("success");
    } catch (err: any) {
      setError(err.message || "Something went wrong. Please try again.");
      setState("error");
    }
  };

  if (state === "success") {
    return (
      <div style={styles.page}>
        <div style={styles.successCard}>
          <div style={styles.successIcon}>✅</div>
          <h2 style={styles.successTitle}>You're in the pipeline.</h2>
          <p style={styles.successText}>{result?.message}</p>
          <div style={styles.scoreRow}>
            <span style={styles.scoreLabel}>Lead Score</span>
            <span style={{ ...styles.scoreValue, color: getScoreColor(result?.score || 0) }}>
              {result?.score}/100
            </span>
            <span style={{ ...styles.tierBadge, ...getTierStyle(result?.tier || "") }}>
              {(result?.tier || "").toUpperCase()}
            </span>
          </div>
          <p style={styles.phoneNote}>
            {form.phone ? "📞 Expect a call within minutes." : "📧 Check your inbox — follow-up coming shortly."}
          </p>
        </div>
      </div>
    );
  }

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
                <label style={styles.label}>Phone (for live demo call)</label>
                <input
                  style={styles.input}
                  type="tel"
                  placeholder="+1 555 000 0000"
                  value={form.phone}
                  onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
                />
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

            <div style={styles.field}>
              <label style={styles.label}>Monthly Lead Volume</label>
              <select
                style={styles.select}
                value={form.lead_volume}
                onChange={e => setForm(f => ({ ...f, lead_volume: e.target.value }))}
              >
                <option value="">Select volume...</option>
                <option value="1-10">1–10 leads/month</option>
                <option value="10-50">10–50 leads/month</option>
                <option value="50-200">50–200 leads/month</option>
                <option value="200+">200+ leads/month</option>
              </select>
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

            {error && <div style={styles.error}>{error}</div>}

            <button style={{ ...styles.cta, ...(state === "loading" ? styles.ctaLoading : {}) }} type="submit" disabled={state === "loading"}>
              {state === "loading" ? "Submitting..." : "🚀 Get My AI Call in 5 Minutes"}
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
              { n: "01", t: "Lead Captured", d: "Form submits to our API. AI scores lead in under 2 seconds." },
              { n: "02", t: "AI Calls Within 5 Min", d: "Vapi voice AI calls your phone while you're at your desk." },
              { n: "03", t: "Deep Critique", d: "Claude analyzes the call. 7 categories scored. Pain points extracted." },
              { n: "04", t: "Gets Smarter", d: "Every 50 calls, the agent rewrites its own script. No human needed." },
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

function getScoreColor(score: number) {
  if (score >= 70) return "#10B981";
  if (score >= 45) return "#F59E0B";
  return "#EF4444";
}

function getTierStyle(tier: string) {
  const map: Record<string, React.CSSProperties> = {
    high: { background: "#065F46", color: "#6EE7B7" },
    medium: { background: "#78350F", color: "#FCD34D" },
    low: { background: "#1F2937", color: "#9CA3AF" },
  };
  return map[tier] || {};
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  page: { minHeight: "100vh", background: "#07070E", color: "white", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" },
  hero: { maxWidth: 900, margin: "0 auto", padding: "3rem 1.5rem 2rem" },
  nav: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "3rem" },
  logo: { fontSize: "1.4rem", fontWeight: 800, color: "#7C3AED" },
  navTag: { fontSize: "0.8rem", color: "#6B7280", border: "1px solid #374151", borderRadius: 20, padding: "3px 10px" },
  headline: { fontSize: "clamp(2.2rem, 5vw, 3.8rem)", fontWeight: 900, lineHeight: 1.1, marginBottom: "1.2rem" },
  gradient: { background: "linear-gradient(90deg, #7C3AED, #3B82F6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" },
  subheadline: { fontSize: "clamp(1rem, 2vw, 1.2rem)", color: "#9CA3AF", lineHeight: 1.7, marginBottom: "2rem", maxWidth: 680 },
  trustRow: { display: "flex", flexWrap: "wrap", gap: 10, marginBottom: "1rem" },
  trustBadge: { fontSize: "0.8rem", color: "#10B981", border: "1px solid rgba(16,185,129,0.3)", borderRadius: 20, padding: "4px 12px" },
  main: { maxWidth: 900, margin: "0 auto", padding: "0 1.5rem 4rem" },
  formCard: { background: "linear-gradient(135deg, #111128 0%, #0D1526 100%)", border: "1px solid rgba(124,58,237,0.3)", borderRadius: 20, padding: "2.5rem", marginBottom: "4rem" },
  formTitle: { fontSize: "1.6rem", fontWeight: 700, marginBottom: 8 },
  formSubtitle: { color: "#9CA3AF", marginBottom: "1.8rem" },
  form: { display: "flex", flexDirection: "column", gap: 16 },
  row: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 },
  field: { display: "flex", flexDirection: "column", gap: 6 },
  label: { fontSize: "0.85rem", color: "#D1D5DB", fontWeight: 500 },
  input: { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, color: "white", padding: "10px 14px", fontSize: "0.95rem", outline: "none" },
  select: { background: "#111128", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, color: "white", padding: "10px 14px", fontSize: "0.95rem", outline: "none" },
  textarea: { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, color: "white", padding: "10px 14px", fontSize: "0.95rem", outline: "none", resize: "vertical" },
  cta: { background: "linear-gradient(135deg, #7C3AED, #3B82F6)", color: "white", border: "none", borderRadius: 12, padding: "14px 28px", fontSize: "1.05rem", fontWeight: 700, cursor: "pointer", marginTop: 8 },
  ctaLoading: { opacity: 0.7, cursor: "not-allowed" },
  legal: { color: "#6B7280", fontSize: "0.75rem", textAlign: "center", marginTop: 4 },
  error: { background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 10, padding: "10px 14px", color: "#FCA5A5", fontSize: "0.9rem" },
  howItWorks: { padding: "2rem 0" },
  sectionTitle: { fontSize: "1.8rem", fontWeight: 700, marginBottom: "2rem", textAlign: "center" },
  steps: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 20 },
  step: { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 14, padding: "1.5rem" },
  stepNum: { fontSize: "2rem", fontWeight: 900, color: "#7C3AED", marginBottom: 10 },
  stepTitle: { fontSize: "1rem", fontWeight: 700, marginBottom: 8 },
  stepDesc: { color: "#9CA3AF", fontSize: "0.88rem", lineHeight: 1.6 },
  footer: { textAlign: "center", padding: "2rem", color: "#4B5563", fontSize: "0.85rem", borderTop: "1px solid rgba(255,255,255,0.05)" },
  successCard: { maxWidth: 480, margin: "4rem auto", background: "linear-gradient(135deg, #111128, #0D1526)", border: "1px solid rgba(16,185,129,0.3)", borderRadius: 20, padding: "3rem", textAlign: "center" },
  successIcon: { fontSize: "3rem", marginBottom: "1rem" },
  successTitle: { fontSize: "1.8rem", fontWeight: 800, marginBottom: "0.5rem" },
  successText: { color: "#9CA3AF", marginBottom: "1.5rem" },
  scoreRow: { display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginBottom: "1rem" },
  scoreLabel: { color: "#9CA3AF", fontSize: "0.9rem" },
  scoreValue: { fontSize: "1.5rem", fontWeight: 800 },
  tierBadge: { padding: "4px 12px", borderRadius: 20, fontSize: "0.78rem", fontWeight: 700 },
  phoneNote: { color: "#6EE7B7", fontSize: "0.9rem", marginTop: "1rem" },
};
