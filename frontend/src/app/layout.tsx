import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Live FIDS - Flight Information Display",
  description: "Gerçek zamanlı Türkiye havalimanları uçuş bilgi ekranı.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr" className="dark">
      <body className={`${inter.variable} font-sans min-h-screen antialiased bg-slate-950 text-slate-200 selection:bg-sky-500/30`}>
        {/* Background Ambient Effect */}
        <div className="fixed inset-0 z-[-1] pointer-events-none">
          <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-sky-900/20 blur-[120px]" />
          <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-900/20 blur-[120px]" />
        </div>

        <main className="max-w-[1920px] mx-auto min-h-screen flex flex-col p-4 md:p-8">
          {children}
        </main>
      </body>
    </html>
  );
}
