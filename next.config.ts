import type { NextConfig } from "next";

// 개발 중에는 /api/* 를 로컬 계산 서버(python dev_api.py, 8000번)로 넘긴다.
// 배포(Vercel)에서는 api/*.py 파이썬 함수가 같은 주소를 맡는다.
const nextConfig: NextConfig = {
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    return [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }];
  },
};

export default nextConfig;
