import type { Metadata } from "next";
import { Suspense } from "react";
import { Fraunces, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import SplashCursor from "@/components/ui/SplashCursor";
import "./globals.css";

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "900"],
  style: ["normal", "italic"],
});

const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Shark-ISR VTOL — Detection-Gated Guidance Autonomy",
  description:
    "A ROS 2 guidance state machine that flies a tri-tiltrotor VTOL from SEARCH to TRACK on its own — gated on onboard detection confidence. Persistent maritime ISR autonomy.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${plexSans.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {children}
        <Suspense fallback={null}>
          <SplashCursor />
        </Suspense>
      </body>
    </html>
  );
}
