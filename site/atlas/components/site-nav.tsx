import Link from "next/link";
import { getCatalog } from "@/lib/catalog";
import { getAtlasProjectContext } from "@/lib/project";

export async function SiteNav() {
  const [{ navigation }, project] = await Promise.all([getCatalog(), getAtlasProjectContext()]);
  const projectLinks = project?.links.slice(0, 3) ?? [];

  return (
    <header className="atlas-nav">
      <Link href="/" className="atlas-wordmark">
        Lenia Atlas
      </Link>
      <nav className="atlas-pill-row" aria-label="Atlas navigation">
        {navigation.map((item) => (
          <Link key={item.href} href={item.href} className="atlas-pill">
            {item.label}
          </Link>
        ))}
        {projectLinks.map((item) => (
          <Link key={item.href} href={item.href} className="atlas-pill atlas-pill-passive">
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
