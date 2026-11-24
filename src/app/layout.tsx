import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "수확계산기", description: "지난 34년 날씨로 내 땅의 농사 손익을 미리 계산하는 수확계산기" };
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="ko"><head><link rel="preconnect" href="https://cdn.jsdelivr.net" crossOrigin="" /><link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css" /></head><body>{children}</body></html>; }
