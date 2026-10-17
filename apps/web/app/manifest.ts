import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Fiona — The Window",
    short_name: "Fiona",
    description: "A finance team for your business, with every action checked by the Guardian.",
    start_url: "/",
    display: "standalone",
    display_override: ["window-controls-overlay", "standalone"],
    background_color: "#f6f7f5",
    theme_color: "#f6f7f5",
    icons: [
      { src: "/icon-192.svg", sizes: "192x192", type: "image/svg+xml", purpose: "any" },
      { src: "/icon-512.svg", sizes: "512x512", type: "image/svg+xml", purpose: "maskable" },
    ],
  };
}
