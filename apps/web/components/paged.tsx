"use client";

import { useState, type ReactNode } from "react";

/**
 * Long registers show a first page and grow on request, so a ledger with thousands of rows
 * stays readable and fast. Every row is still reachable; nothing is dropped.
 */
function useMore(total: number, pageSize: number) {
  const [shown, setShown] = useState(Math.min(total, pageSize));
  const more = Math.min(pageSize, total - shown);
  return { shown, more, showMore: () => setShown((value) => Math.min(total, value + pageSize)), showAll: () => setShown(total) };
}

function MoreBar({ shown, total, more, noun, onMore, onAll }: { shown: number; total: number; more: number; noun: string; onMore: () => void; onAll: () => void }) {
  if (total <= shown) return total > 0 ? <p className="sk-more-note">All {total.toLocaleString("en-US")} {noun} shown</p> : null;
  return (
    <div className="sk-more">
      <span>Showing {shown.toLocaleString("en-US")} of {total.toLocaleString("en-US")} {noun}</span>
      <div>
        <button type="button" className="button button-secondary" onClick={onMore}>Show {more.toLocaleString("en-US")} more</button>
        {total - shown > more && <button type="button" className="sk-link-button" onClick={onAll}>Show all</button>}
      </div>
    </div>
  );
}

export function PagedTable({ headers, rows, pageSize = 20, noun = "rows", numeric = [], caption }: { headers: string[]; rows: ReactNode[][]; pageSize?: number | undefined; noun?: string | undefined; numeric?: number[] | undefined; caption?: string | undefined }) {
  const { shown, more, showMore, showAll } = useMore(rows.length, pageSize);
  return (
    <>
      <div className="data-table-wrap sk-table-wrap">
        <table className="data-table sk-table">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead><tr>{headers.map((header, index) => <th key={header} className={numeric.includes(index) ? "is-num" : undefined} scope="col">{header}</th>)}</tr></thead>
          <tbody>
            {rows.slice(0, shown).map((row, index) => (
              <tr key={index} className={index >= pageSize ? "sk-row-new" : undefined} style={index >= pageSize ? { animationDelay: `${Math.min((index % pageSize) * 18, 300)}ms` } : undefined}>
                {row.map((cell, cellIndex) => <td key={cellIndex} className={numeric.includes(cellIndex) ? "is-num" : undefined}>{cell}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <MoreBar shown={shown} total={rows.length} more={more} noun={noun} onMore={showMore} onAll={showAll} />
    </>
  );
}

export function PagedList({ items, pageSize = 10, noun = "items", className = "option-list" }: { items: ReactNode[]; pageSize?: number | undefined; noun?: string | undefined; className?: string | undefined }) {
  const { shown, more, showMore, showAll } = useMore(items.length, pageSize);
  return (
    <>
      <div className={className}>{items.slice(0, shown)}</div>
      <MoreBar shown={shown} total={items.length} more={more} noun={noun} onMore={showMore} onAll={showAll} />
    </>
  );
}
