"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import "./vendor/folder/Folder.css";

// Client-only: the folder derives its shades with a canvas, which the server can't, so a
// server render would hydrate with the wrong colours.
const Folder = dynamic(() => import("./vendor/folder/Folder"), {
  ssr: false,
  loading: () => <div className="agent-folder-placeholder" aria-hidden="true" />,
});
import "./agent-folder.css";

export interface FolderAgent {
  name: string;
  role: string;
  level: string;
  code: string;
  color: string;
}

const STORAGE_KEY = "fiona:agent-folder";

/**
 * The agent roster as a folder in the right panel. Open (the default) it stacks one page per
 * agent so every name stays visible; clicking a page brings it up close. The open state is
 * remembered per browser.
 */
export function AgentFolder({ agents }: { agents: FolderAgent[] }) {
  const [open, setOpen] = useState(true);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      try {
        const saved = window.localStorage.getItem(STORAGE_KEY);
        if (saved !== null) setOpen(saved === "true");
      } catch {
        // Storage is optional
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  function onOpenChange(next: boolean) {
    setOpen(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, String(next));
    } catch {
      // Storage is optional
    }
  }

  return (
    <div className={`agent-folder ${open ? "agent-folder-open" : ""}`}>
      <Folder
        label={`${agents.length} agents`}
        tabPosition="left"
        layout="stack"
        theme="light"
        color="#2e80e6"
        size={1.05}
        open={open}
        onOpenChange={onOpenChange}
        closeOnOutsideClick={false}
        draggable={false}
        tilt={0.35}
      >
        {/* The front page is the first child; reverse so the roster reads top-down in its usual order. */}
        {[...agents].reverse().map((agent) => (
          <article className="agent-page" key={agent.name} aria-label={`${agent.name}: ${agent.role}. ${agent.level}.`}>
            <header className="agent-page-head">
              <span className={`agent-page-avatar ${agent.color}`}>
                {agent.code}
                <i className="agent-page-live" />
              </span>
              <strong>{agent.name}</strong>
            </header>
            <span className="agent-page-level">{agent.level}</span>
            <p className="agent-page-role">{agent.role}</p>
            <span className="agent-page-rule" />
            <span className="agent-page-line" style={{ width: "88%" }} />
            <span className="agent-page-line" style={{ width: "72%" }} />
            <span className="agent-page-line" style={{ width: "80%" }} />
          </article>
        ))}
      </Folder>
    </div>
  );
}
