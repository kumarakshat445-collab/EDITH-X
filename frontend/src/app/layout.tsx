import type { Metadata } from "next";
import "./globals.css";
import { WebSocketProvider } from "@/lib/websocket";

export const metadata: Metadata = {
  title: "EDITH-X V2 Command Center",
  description: "Autonomous sentient-tier operating core and Nexus Poly-Engine HUD",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <WebSocketProvider>{children}</WebSocketProvider>
      </body>
    </html>
  );
}
