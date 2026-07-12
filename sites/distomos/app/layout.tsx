import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://distomostech.com"),
  title: "Distomos — See the shape of what’s next",
  description: "Independent intelligence for navigating the AI economy.",
  openGraph: { title: "Distomos", description: "See the shape of what’s next.", images: ["/og.png"] },
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
