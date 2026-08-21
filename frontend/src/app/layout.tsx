import type { Metadata, Viewport } from "next";
import "./globals.css";
import { BarraNavegacion } from "@/components/barra-navegacion";
import { BarraComandos } from "@/components/barra-comandos";
import { BotonTema } from "@/components/boton-tema";

export const metadata: Metadata = {
  title: "HomeVault AI",
  description: "Gestión inteligente del hogar sobre un vault Markdown",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "HomeVault",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf9f7" },
    { media: "(prefers-color-scheme: dark)", color: "#0e1013" },
  ],
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

// Script inline que aplica la clase "dark" antes del primer pintado para
// evitar el parpadeo: prioriza la elección guardada y si no, la del sistema.
const scriptTema = `(function(){try{var t=localStorage.getItem("tema");var d=t==="dark"||(!t&&window.matchMedia("(prefers-color-scheme: dark)").matches);if(d)document.documentElement.classList.add("dark")}catch(e){}})()`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: scriptTema }} />
      </head>
      <body className="min-h-dvh bg-arena-50 text-carbon-950 antialiased dark:bg-carbon-950 dark:text-arena-100">
        <div className="mx-auto flex min-h-dvh w-full max-w-5xl flex-col px-4 pb-24 pt-4 sm:px-6">
          <header className="mb-4 flex items-center justify-between">
            <h1 className="text-xl font-bold tracking-tight">
              HomeVault <span className="text-emerald-600">AI</span>
            </h1>
            <BotonTema />
          </header>
          <main className="flex-1">{children}</main>
        </div>
        <BarraNavegacion />
        <BarraComandos />
      </body>
    </html>
  );
}
