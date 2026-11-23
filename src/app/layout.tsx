import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "수확계산기", description: "지난 34년 날씨로 내 땅의 농사 손익을 미리 계산하는 수확계산기" };
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="ko"><body>{children}</body></html>; }
