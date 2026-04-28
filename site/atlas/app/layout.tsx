import type { Metadata } from "next";
import type { ReactNode } from "react";
import "@/app/globals.css";
import { AtlasShell } from "@/components/atlas-shell";
import { getAtlasProjectContext } from "@/lib/project";

export async function generateMetadata(): Promise<Metadata> {
  const project = await getAtlasProjectContext();
  return {
    title: project ? `Lenia Atlas | ${project.title}` : "Lenia Atlas",
    description:
      project?.summary ??
      "Museum-grade atlas scaffold for Lenia taxa, ecologies, and creature telemetry."
  };
}

type RootLayoutProps = {
  children: ReactNode;
};

export default async function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>
        <AtlasShell>{children}</AtlasShell>
      </body>
    </html>
  );
}
