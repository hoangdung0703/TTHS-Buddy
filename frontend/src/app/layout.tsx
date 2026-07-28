import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "TTHS Buddy",
  description: "AI study assistant scaffold for criminal procedure law"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
