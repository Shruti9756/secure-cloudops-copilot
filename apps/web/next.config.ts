import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: process.env.WEB_OUTPUT_MODE === "export" ? "export" : "standalone",
};

export default nextConfig;
