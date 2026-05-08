import Landing from "./Landing";

// /app/ root: signed-out visitors see the marketing landing; signed-in
// visitors get bounced to their dashboard. The bounce lives inside
// Landing so the redirect happens before any markup mounts.
export default function Home() {
  return <Landing />;
}
