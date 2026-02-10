import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Disable the Next.js dev indicator (N logo in corner)
  devIndicators: false,
  
  // Note: For local network access during development, you may need to add
  // your machine's IP to allowedDevOrigins, e.g.:
  // allowedDevOrigins: ["http://192.168.x.x", "192.168.x.x"],
};

export default nextConfig;
