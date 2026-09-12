/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    // Proxy API calls to the FastAPI backend during local development so the
    // dashboard can call relative /api/* paths. Override with
    // NEXT_PUBLIC_API_BASE when the backend lives elsewhere.
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;