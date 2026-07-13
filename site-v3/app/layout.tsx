import type { Metadata } from "next";
import {
  Fraunces,
  IBM_Plex_Mono,
  IBM_Plex_Sans,
  Saira_Condensed,
} from "next/font/google";
import "./globals.css";

const saira = Saira_Condensed({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-saira",
});
const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-sans",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
});
const fraunces = Fraunces({
  subsets: ["latin"],
  style: ["italic"],
  weight: ["400", "500"],
  variable: "--font-fraunces",
});

export const metadata: Metadata = {
  title: "Shark-ISR VTOL — Autonomous Aerial Shark Surveillance",
  description:
    "A tri-tiltrotor VTOL that patrols a swim zone, detects sharks onboard with a 13-TOPS NPU, and switches to a tracking orbit on its own. No video downlink in the decision loop.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body
        className={`${saira.variable} ${plexSans.variable} ${plexMono.variable} ${fraunces.variable}`}
      >
        {children}
      </body>
    </html>
  );
}
