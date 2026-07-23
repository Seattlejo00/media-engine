import type { Metadata } from "next";
import Link from "next/link";

const contextWindowUrl = "https://contextwindow.distomostech.com";
const inquiryEmail = "james@disomostech.com";
const inquiryHref = `mailto:${inquiryEmail}?subject=Business%20inquiry%20for%20Distomos`;

export const metadata: Metadata = {
  title: "Business inquiries — Distomos",
  description: "Partnerships, sponsorships, and business inquiries for Distomos and The Context Window.",
  alternates: { canonical: "/business" },
};

const inquiryTypes = [
  ["01", "Partnerships", "Distribution, platform, and editorial collaborations that make The Context Window more useful and more widely available."],
  ["02", "Sponsorships", "Thoughtful brand integrations for organizations that want to reach people following consequential AI developments."],
  ["03", "Other inquiries", "Research collaborations, press, investment, and ideas that do not fit neatly into a predefined category."],
];

export default function Business() {
  return <main className="business-page">
    <section className="business-hero">
      <div className="business-art" />
      <div className="business-shade" />
      <header>
        <Link className="wordmark" href="/" aria-label="Distomos home"><i>D</i><span>DISTOMOS</span></Link>
        <nav><Link href="/">Home</Link><a href={contextWindowUrl} target="_blank" rel="noopener noreferrer">The Context Window</a></nav>
        <a className="nav-cta" href={inquiryHref}>Get in touch <b>↗</b></a>
      </header>
      <div className="business-copy shell">
        <p className="overline"><span /> BUSINESS INQUIRIES</p>
        <h1>Good work starts<br />with <em>context.</em></h1>
        <div className="business-intro">
          <p>Distomos is building a more useful way to understand what is changing in AI. If your organization sees a meaningful way to work together, we would like to hear it.</p>
          <a href={inquiryHref}>{inquiryEmail} <b>↗</b></a>
        </div>
      </div>
    </section>
    <section className="business-paths shell" aria-labelledby="business-paths-title">
      <div><p className="index">01 / WAYS TO WORK TOGETHER</p><h2 id="business-paths-title">A direct line for<br /><em>serious ideas.</em></h2></div>
      <ol>{inquiryTypes.map(([number, title, description]) => <li key={number}><span>{number}</span><div><h3>{title}</h3><p>{description}</p></div></li>)}</ol>
    </section>
    <section className="business-contact shell">
      <p className="index">02 / START A CONVERSATION</p>
      <div><h2>Tell us what you are<br />trying to make possible.</h2><p>Include a short description of your organization, the opportunity, and any timing that matters. We will respond if there is a strong fit.</p><a href={inquiryHref}>Write to Distomos <b>↗</b></a></div>
    </section>
    <footer className="shell"><Link className="wordmark" href="/"><i>D</i><span>DISTOMOS</span></Link><p>Publisher of The Context Window.<br />Signal over noise, every morning.</p><nav><Link href="/">Home</Link><a href={contextWindowUrl} target="_blank" rel="noopener noreferrer">The Context Window</a><a href={inquiryHref}>Email us</a></nav><div className="footer-bottom"><span>© 2026 DISTOMOS</span><span>BUSINESS INQUIRIES</span><span>DENVER, COLORADO</span></div></footer>
  </main>;
}
