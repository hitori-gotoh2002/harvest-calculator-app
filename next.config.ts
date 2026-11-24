import type { NextConfig } from "next";

// 개발 중에는 /api/* 를 로컬 계산 서버(python dev_api.py, 8000번)로 넘긴다.
// 배포(Vercel)에서는 api/*.py 파이썬 함수가 같은 주소를 맡는다.
// 로컬 계산 서버는 한 번에 하나씩 계산해 요청이 줄을 서므로, 넘겨 주고 기다리는 시간을 30초(기본)에서 5분으로 늘린다.
const nextConfig: NextConfig = {
  experimental: { proxyTimeout: 300_000 },
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    return [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }];
  },
};

export default nextConfig;
