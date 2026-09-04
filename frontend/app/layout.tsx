import type { Metadata, Viewport } from "next";
import "@fontsource-variable/public-sans/wght.css";
import "./globals.css";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export const metadata: Metadata = {
  metadataBase: new URL("https://civicscope-gold.vercel.app"),
  title: "CivicScope — GTA Housing Affordability Explorer",
  description:
    "Interactive dashboard mapping rent burden, income, and CMHC housing data for 25 GTA municipalities and 1,334 census tracts.",
  icons: { icon: "/favicon.svg" },
  openGraph: {
    title: "CivicScope — GTA Housing Affordability Explorer",
    description:
      "Explore rent burden, income, and CMHC rental data across 25 municipalities and 1,334 census tracts in the Greater Toronto Area.",
    siteName: "CivicScope",
    type: "website",
    locale: "en_CA"
  },
  twitter: {
    card: "summary_large_image",
    title: "CivicScope — GTA Housing Affordability Explorer",
    description:
      "Explore rent burden, income, and CMHC rental data across the Greater Toronto Area."
  }
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem("civicscope-theme");if(t==="dark"||(!t&&matchMedia("(prefers-color-scheme:dark)").matches))document.documentElement.classList.add("dark")}catch(e){}})()`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
