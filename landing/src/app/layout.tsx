import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Shango Revenue Systems — Stop Losing Leads. Let AI Close Them.",
  description: "Shango Revenue Systems scores every inbound lead, calls them within 5 minutes, and gets smarter after every call. Zero SDRs. Zero missed follow-ups.",
  openGraph: {
    title: "Shango Revenue Systems — Autonomous Sales Agent",
    description: "Let AI score, call, and close your leads while you sleep.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, padding: 0 }}>{children}</body>
    </html>
  );
}
