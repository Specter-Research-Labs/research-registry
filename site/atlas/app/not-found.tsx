import Link from "next/link";

export default function NotFoundPage() {
  return (
    <div className="empty-state">
      <span className="detail-kicker">Atlas</span>
      <h1>Specimen not found</h1>
      <p>The requested specimen is not present in the current atlas catalog or published replay set.</p>
      <Link href="/" className="atlas-pill atlas-pill-strong">
        Return to collection
      </Link>
    </div>
  );
}
