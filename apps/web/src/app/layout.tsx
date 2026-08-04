import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SecureCloudOps Copilot",
  description: "Secure AI incident investigation for AWS engineering teams.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
