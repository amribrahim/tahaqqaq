import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export: deployed as plain files on Cloudflare Pages; all data comes from the API.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};

export default nextConfig;
