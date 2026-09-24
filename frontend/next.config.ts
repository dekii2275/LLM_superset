import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: ["localhost", "127.0.0.1", "localhost:43117", "127.0.0.1:43117"],
};

export default nextConfig;
