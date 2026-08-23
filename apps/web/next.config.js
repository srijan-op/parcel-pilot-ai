/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Smaller production image for Docker / EC2
  output: "standalone",
};

module.exports = nextConfig;
