"use client";

import { useEffect, useState } from "react";

export default function Home() {
  const [status, setStatus] = useState("checking...");

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => setStatus(d.status))
      .catch(() => setStatus("backend unreachable"));
  }, []);

  return (
    <main style={{ padding: "2rem", maxWidth: 720, margin: "0 auto" }}>
      <h1>ClearCurb</h1>
      <p>Accessible route planning that avoids missing curb cuts, steep grades, and broken sidewalks.</p>
      <p>Backend status: {status}</p>
    </main>
  );
}
