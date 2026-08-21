import type { Metadata, Viewport } from "next";
import "./globals.css";
import { BarraNavegacion } from "@/components/barra-navegacion";
import { BarraComandos } from "@/components/barra-comandos";
import { PerfilProvider } from "@/components/perfil-context";
import { PerfilGate } from "@/components/perfil-gate";

export const metadata: Metadata = {
  title: "HomeVault AI",
  description: "Gestión inteligente del hogar sobre un vault Markdown",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "HomeVault",
  },
};

export const viewport: Viewport = {
  themeColor: [{ media: "(prefers-color-scheme: dark)", color: "#020617" }],
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

// Fuerza el modo oscuro antes del primer pintado para eliminar cualquier
// parpadeo de tema claro. La aplicación usa siempre el tema oscuro premium.
const scriptTema = `(function(){try{document.documentElement.classList.add("dark")}catch(e){}})()`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" className="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: scriptTema }} />
      </head>
      <body className="min-h-dvh bg-slate-950 text-slate-100 antialiased">
        <PerfilProvider>
          <PerfilGate>
            <div className="mx-auto flex min-h-dvh w-full max-w-5xl flex-col px-4 pb-28 pt-5 sm:px-6">
              <header className="mb-6 flex items-center justify-between">
                <h1 className="text-xl font-bold tracking-tight">
                  HomeVault <span className="text-emerald-500">AI</span>
                </h1>
              </header>
              <main className="flex-1">{children}</main>
            </div>
            <BarraNavegacion />
            <BarraComandos />
          </PerfilGate>
        </PerfilProvider>
      </body>
    </html>
  );
}
