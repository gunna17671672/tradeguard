import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // `npm run build` emits a fully static site in out/, served by FastAPI in
  // production (single container). Dev mode still talks to :8000 directly
  // (see src/lib/api.ts). trailingSlash makes each page a directory with an
  // index.html, which is what StaticFiles(html=True) resolves.
  output: "export",
  trailingSlash: true,
};

export default nextConfig;
