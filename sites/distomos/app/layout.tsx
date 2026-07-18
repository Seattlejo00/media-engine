import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://distomostech.com"),
  title: "Distomos — See the shape of what’s next",
  description: "Distomos publishes The Context Window, a fully automated daily briefing on what changed in AI and why it matters.",
  alternates: { canonical: "/" },
  openGraph: {
    title: "Distomos — See the shape of what’s next",
    description: "The essential daily briefing on what changed in AI and why it matters.",
    type: "website",
    url: "/",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "Distomos — See the shape of what’s next" }],
  },
  twitter: { card: "summary_large_image", images: ["/og.png"] },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
