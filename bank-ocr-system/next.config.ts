import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  typescript: {
    // Next.js 16 Turbopack can generate corrupted route types in .next/dev/types/routes.d.ts
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
