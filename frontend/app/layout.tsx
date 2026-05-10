import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CivicScope",
  description: "Greater Toronto Area housing affordability and civic geospatial analytics"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
