import { Compass, Droplets, LayoutGrid, MapPin, Search, ShieldCheck } from "lucide-react";
import * as React from "react";
import { searchIndex, type SearchItem, type SearchKind } from "@/lib/search";

const KIND: Record<SearchKind, { label: string; icon: React.ComponentType<{ size?: number }> }> = {
  view: { label: "View", icon: LayoutGrid },
  region: { label: "Region", icon: Compass },
  detection: { label: "Detection", icon: MapPin },
  river: { label: "River", icon: Droplets },
  protected_area: { label: "Protected area", icon: ShieldCheck },
};

/**
 * Ctrl/Cmd+K: jump to a region, detection, river, protected area or view.
 * Search and navigation only — there is no free-text question answering here.
 */
export function CommandPalette(props: {
  open: boolean; onClose: () => void; index: SearchItem[]; onPick: (item: SearchItem) => void;
}) {
  // Mounted only while open, so every opening starts from an empty query.
  return props.open ? <PaletteBody {...props} /> : null;
}

function PaletteBody({ onClose, index, onPick }: {
  onClose: () => void; index: SearchItem[]; onPick: (item: SearchItem) => void;
}) {
  const [query, setQuery] = React.useState("");
  const [active, setActive] = React.useState(0);
  const input = React.useRef<HTMLInputElement>(null);
  const results = React.useMemo(() => searchIndex(index, query), [index, query]);
  const listId = React.useId();

  // Focus moves in on open and returns to where it was on close.
  React.useEffect(() => {
    const restore = document.activeElement as HTMLElement | null;
    input.current?.focus();
    return () => restore?.focus?.();
  }, []);

  const pick = (item: SearchItem | undefined) => { if (item) { onPick(item); onClose(); } };

  return (
    <div className="gn-palette-root" onKeyDown={event => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onClose(); }
      else if (event.key === "ArrowDown") { event.preventDefault(); setActive(i => Math.min(i + 1, results.length - 1)); }
      else if (event.key === "ArrowUp") { event.preventDefault(); setActive(i => Math.max(i - 1, 0)); }
      else if (event.key === "Enter") { event.preventDefault(); pick(results[active]); }
      else if (event.key === "Tab") event.preventDefault(); // focus stays in the palette
    }}>
      <div className="gn-palette-scrim gn-fade" onClick={onClose} aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-label="Search regions, detections, rivers and protected areas"
        className="gn-palette gn-pop">
        <div className="gn-palette-input">
          <Search size={16} aria-hidden="true" />
          <input ref={input} value={query} onChange={e => { setQuery(e.target.value); setActive(0); }}
            placeholder="Search regions, detections, rivers, protected areas…"
            role="combobox" aria-expanded="true" aria-controls={listId}
            aria-activedescendant={results[active] ? `${listId}-${active}` : undefined} />
          <kbd>Esc</kbd>
        </div>
        <ul id={listId} role="listbox" className="gn-palette-list">
          {results.map((item, i) => {
            const kind = KIND[item.kind];
            return (
              <li key={`${item.kind}:${item.id}`} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                onMouseMove={() => setActive(i)} onClick={() => pick(item)}>
                <kind.icon size={14} />
                <span className="gn-palette-label">{item.label}</span>
                <span className="gn-palette-detail">{item.detail}</span>
                <span className="gn-palette-kind">{kind.label}</span>
              </li>
            );
          })}
          {!results.length && <li className="gn-palette-empty" role="presentation">
            No match in the loaded data. Detections, rivers and protected areas are searched in the open region only.
          </li>}
        </ul>
      </div>
    </div>
  );
}
