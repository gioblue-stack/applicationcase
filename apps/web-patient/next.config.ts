import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Режим разработки: сайт открывают с телефона в той же Wi-Fi-сети по адресу компьютера.
  allowedDevOrigins: ["192.168.*.*", "10.*.*.*", "172.*.*.*", "*.local"],
};

export default nextConfig;
