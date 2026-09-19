import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import "./modernist.css";
import "./globals.css";

const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  weight: ["400", "600", "800"],
});

export const metadata: Metadata = {
  title: "ClearCurb",
  description:
    "Accessible route planning that avoids missing curb cuts, steep grades, and broken sidewalks.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={archivo.variable}>
      <body>{children}</body>
    </html>
  );
}
