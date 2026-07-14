import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export ("output: 'export'") arrives with M4 packaging; dev mode
  // talks to the FastAPI server on :8000 directly (see src/lib/api.ts).
};

export default nextConfig;
