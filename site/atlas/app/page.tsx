import Link from "next/link";
import { HeroWall } from "@/components/hero-wall";
import { Reveal } from "@/components/reveal";
import { getCatalog, getTaxa } from "@/lib/catalog";
import { getAtlasProjectContext } from "@/lib/project";

export default async function AtlasLandingPage() {
  const [catalog, families, project] = await Promise.all([
    getCatalog(),
    getTaxa("family"),
    getAtlasProjectContext()
  ]);
  const { headline, subheadline } = catalog;
  const firstFamily = families[0]?.slug;

  return (
    <div className="atlas-stack">
      <section className="landing-hero">
        <Reveal className="landing-copy">
          <span className="detail-kicker">Collection</span>
          <h1>{headline}</h1>
          <p className="detail-lead">{subheadline}</p>
          <div className="cta-row">
            <Link href="/creatures" className="atlas-pill atlas-pill-strong">
              Browse collection
            </Link>
            <Link href="/ecology" className="atlas-pill">
              Browse ecology
            </Link>
            <Link href={firstFamily ? `/family/${firstFamily}` : "/ecology"} className="atlas-pill atlas-pill-passive">
              Enter taxonomy
            </Link>
          </div>
        </Reveal>
        <HeroWall />
      </section>

      <section className="summary-band">
        <div>
          <span>Specimens</span>
          <strong>{catalog.creatures.length}</strong>
        </div>
        <div>
          <span>Families</span>
          <strong>{families.length}</strong>
        </div>
        <div>
          <span>Mode</span>
          <strong>Filmic + telemetry</strong>
        </div>
      </section>

      {project ? (
        <section className="taxon-showcase">
          <article className="taxon-card">
            <span className="detail-kicker">Registry Context</span>
            <h2>{project.title}</h2>
            <p>{project.summary}</p>
            <div className="cta-row">
              {project.links.map((link) => (
                <Link key={link.href} href={link.href} className="atlas-pill atlas-pill-passive">
                  {link.label}
                </Link>
              ))}
            </div>
          </article>
          <article className="taxon-card">
            <span className="detail-kicker">Proof Path</span>
            <h2>{project.gateState ?? "Informational"}</h2>
            <p>
              {project.proofSummary} Release: {project.releaseStage}. Last activity: {project.lastActivity}.
            </p>
          </article>
        </section>
      ) : null}

      <section className="taxon-showcase">
        {families.map((family) => (
          <article key={family.slug} className="taxon-card">
            <span className="detail-kicker">{family.kicker}</span>
            <h2>{family.name}</h2>
            <p>{family.description}</p>
            <Link href={`/family/${family.slug}`} className="atlas-text-link">
              Open family
            </Link>
          </article>
        ))}
      </section>
    </div>
  );
}
