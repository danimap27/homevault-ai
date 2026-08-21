import withPWAInit from "@ducanh2912/next-pwa";

// PWA con service worker precache; desactivado en desarrollo para no
// interferir con HMR.
const withPWA = withPWAInit({
  dest: "public",
  disable: process.env.NODE_ENV === "development",
  register: true,
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone", // requerido por el Dockerfile multi-stage
  reactStrictMode: true,
};

export default withPWA(nextConfig);
