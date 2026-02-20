import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow cross-origin video embeds from the Railway backend
  async headers() {
    return [
      {
        source: "/api/:path*",
        headers: [
          { key: "Access-Control-Allow-Origin", value: "*" },
        ],
      },
    ];
  },
};

export default nextConfig;
