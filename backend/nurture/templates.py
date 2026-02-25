"""
Aurora 1.0 — Nurture Email Templates
HTML email wrapper + template hints used by the OpenClaw NurtureAgent.
"""

# ── Branded HTML wrapper ──────────────────────────────────────────────────────

_HTML_WRAPPER = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f4f4f5; margin: 0; padding: 0; }}
  .outer {{ max-width: 560px; margin: 32px auto; }}
  .card  {{ background: #ffffff; border-radius: 12px; padding: 36px 40px;
            border: 1px solid #e5e7eb; }}
  .logo  {{ font-size: 1.1rem; font-weight: 800; color: #7C3AED; margin-bottom: 28px; }}
  .body  {{ color: #374151; font-size: 0.95rem; line-height: 1.75;
            white-space: pre-wrap; }}
  .cta   {{ display: inline-block; margin-top: 24px; padding: 12px 24px;
            background: linear-gradient(135deg,#7C3AED,#3B82F6); color: #fff;
            border-radius: 8px; text-decoration: none; font-weight: 700;
            font-size: 0.9rem; }}
  .footer {{ margin-top: 32px; color: #9ca3af; font-size: 0.75rem; text-align: center; }}
  .divider{{ border: none; border-top: 1px solid #e5e7eb; margin: 24px 0; }}
</style>
</head>
<body>
<div class="outer">
  <div class="card">
    <div class="logo">🛰 Shango Revenue Systems</div>
    <div class="body">{body}</div>
    <a href="{cta_url}" class="cta">Book a 15-min call →</a>
    <hr class="divider">
    <div class="footer">
      Shango Revenue Systems · AI-Powered Sales Development<br>
      <a href="{unsubscribe_url}" style="color:#9ca3af">Unsubscribe</a>
    </div>
  </div>
</div>
</body>
</html>
"""


def render_email_html(
    subject: str,
    body_text: str,
    lead_name: str,
    template_type: str = "generic",
) -> str:
    """Wrap a plain-text body in the branded HTML email template."""
    booking_url = "https://cal.com/shango-revenue-systems"
    unsubscribe_url = "https://shango.ai/unsubscribe"
    return _HTML_WRAPPER.format(
        subject=subject,
        body=body_text,
        cta_url=booking_url,
        unsubscribe_url=unsubscribe_url,
    )


# ── Template prompt hints (used by OpenClaw NurtureAgent) ────────────────────
# These describe the goal/tone for each template; the AI fills in the content.

TEMPLATE_HINTS: dict[str, dict] = {
    "hot_intro": {
        "goal": "Immediately follow up on the AI demo call. Reference specific pain points. Propose a 15-min deep-dive.",
        "tone": "Urgent, personal, concise. Mention the call. Reference their exact challenge.",
        "cta": "Book a 15-min strategy session this week.",
        "max_words": 120,
    },
    "hot_followup_call": {
        "goal": "Pre-call briefing email sent 2 hours before the follow-up call. Agenda + what to expect.",
        "tone": "Warm, preparatory, sets expectations.",
        "cta": "Confirm the call time or reply to reschedule.",
        "max_words": 100,
    },
    "hot_case_study": {
        "goal": "Share a relevant case study or social proof tied to their industry/pain point.",
        "tone": "Authoritative but conversational. One specific result (metric).",
        "cta": "Replies with: 'Want to see your numbers?'",
        "max_words": 130,
    },
    "hot_final": {
        "goal": "Final touch. Light urgency. Leave the door open.",
        "tone": "Respectful, not pushy. Acknowledge they're busy.",
        "cta": "Same link to book. One last ask.",
        "max_words": 90,
    },
    "warm_intro": {
        "goal": "Introduce Shango Revenue Systems following the demo call. Focus on their #1 pain point.",
        "tone": "Professional-warm, specific to their challenge.",
        "cta": "Offer a free pipeline audit or report.",
        "max_words": 130,
    },
    "warm_value_add": {
        "goal": "Provide genuine value — a tip, checklist, or insight relevant to their sales challenge.",
        "tone": "Helpful, non-salesy. Give before asking.",
        "cta": "Soft: 'Curious if this matches your situation?'",
        "max_words": 140,
    },
    "warm_check_in": {
        "goal": "Check in before the follow-up call. Build warmth.",
        "tone": "Human, brief, low-pressure.",
        "cta": "Offer to reschedule if the time doesn't work.",
        "max_words": 80,
    },
    "warm_final": {
        "goal": "Final nurture email. Last outreach for the sequence.",
        "tone": "Gracious exit, keep relationship warm for future.",
        "cta": "Re-engage whenever the timing is right.",
        "max_words": 100,
    },
    "cold_intro": {
        "goal": "Low-pressure first email for lower-scored lead. Educational, not salesy.",
        "tone": "Gentle, helpful. Share one useful resource.",
        "cta": "Soft: 'Let me know if this is useful.'",
        "max_words": 120,
    },
    "cold_content": {
        "goal": "Content nurture. Send a relevant article, benchmark, or insight.",
        "tone": "Educational, zero sales pressure.",
        "cta": "No hard CTA. Light: 'Happy to share more.'",
        "max_words": 110,
    },
    "cold_reactivation": {
        "goal": "Reactivation attempt. Ask if things have changed and timing is better now.",
        "tone": "Empathetic, direct. Acknowledge time has passed.",
        "cta": "15-min call to re-assess fit.",
        "max_words": 100,
    },
}
