import type { MetadataRoute } from "next";

/** Makes OxisTrack installable: desktop icon and its own window on Windows/macOS, home screen on phones. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "OxisTrack",
    short_name: "OxisTrack",
    description: "Know what changed. Know what's missing. Know what to do next.",
    id: "/",
    start_url: "/overview",
    scope: "/",
    display: "standalone",
    background_color: "#09090B",
    theme_color: "#09090B",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
