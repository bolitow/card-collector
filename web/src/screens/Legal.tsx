import { ChevronLeft } from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";

import conditions from "@/legal/conditions.md?raw";
import confidentialite from "@/legal/confidentialite.md?raw";
import mentions from "@/legal/mentions.md?raw";
import { t } from "@/i18n";

const PAGES: Record<string, string> = { conditions, confidentialite, mentions };

/** Documents légaux (D-01) : projets rédigés en Markdown simple — titres, paragraphes, listes. */
export function Legal() {
  const { page = "" } = useParams();
  const source = PAGES[page];
  if (!source) return <Navigate to="/" replace />;
  const blocks: React.ReactNode[] = [];
  let items: string[] = [];
  const flush = () => {
    if (items.length) blocks.push(<ul key={blocks.length}>{items.map((item) => <li key={item}>{item}</li>)}</ul>);
    items = [];
  };
  for (const line of source.split("\n")) {
    if (line.startsWith("- ")) {
      items.push(line.slice(2));
      continue;
    }
    flush();
    if (line.startsWith("# ")) blocks.push(<h1 key={blocks.length} className="title medium">{line.slice(2)}</h1>);
    else if (line.startsWith("## ")) blocks.push(<h2 key={blocks.length} className="heading" style={{ marginTop: 12 }}>{line.slice(3)}</h2>);
    else if (line.trim()) blocks.push(<p key={blocks.length}>{line}</p>);
  }
  flush();
  return (
    <main className="screen bare stack">
      <Link to="/" className="back">
        <ChevronLeft size={16} aria-hidden="true" />
        {t("app.name")}
      </Link>
      {blocks}
    </main>
  );
}
