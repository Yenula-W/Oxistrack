import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Toaster } from "sonner";
import "@fontsource/plus-jakarta-sans/600.css";
import "@fontsource/plus-jakarta-sans/700.css";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "OxisTrack", template: "%s · OxisTrack" },
  description: "Know what changed. Know what's missing. Know what to do next.",
  applicationName: "OxisTrack",
  appleWebApp: { capable: true, title: "OxisTrack", statusBarStyle: "black-translucent" },
};
export const viewport: Viewport = { themeColor: "#09090B" };
// The manifest (src/app/manifest.ts) and these tags make the app installable on desktop and phones.

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="font-sans">
        <Providers>{children}</Providers>
        <Toaster theme="dark" position="bottom-right" toastOptions={{
          style: { background: "#18181B", border: "1px solid #3F3F46", color: "#FAFAFA" } }} />
      </body>
    </html>
  );
}
