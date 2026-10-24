import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title:
    "EquityVal AI — Algorithmic Real Estate Appraisal Bias & Reconsideration of Value (ROV) Auditor",
  description:
    "Eliminate the $48,000 minority homeownership appraisal gap with FHFA/HUD Form 1004 NLP auditing, Gemini Vision UAD C1-C6 condition scoring, and spatial hedonic ROV dossiers.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-slate-950 text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
