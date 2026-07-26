/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: {
    // Lint is run as its own CI step; don't fail `next build` on lint warnings.
    ignoreDuringBuilds: false,
  },
};

export default nextConfig;
