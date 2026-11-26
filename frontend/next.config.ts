import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  productionBrowserSourceMaps: false,
  // Local runs only. In deployment Nginx routes /api to the backend and API_ORIGIN is unset.
  async rewrites() {
    const origin = process.env.API_ORIGIN ?? (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "");
    return origin ? [{ source: "/api/:path*", destination: `${origin}/api/:path*` }] : [];
  },
};

export default config;
