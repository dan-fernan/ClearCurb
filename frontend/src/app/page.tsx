import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import "./landing.css";

export const metadata: Metadata = {
  title: "ClearCurb · Accessible routes for NYC",
};

const STEPS = [
  {
    title: "Pick two points",
    body: "Click the map to set where you are starting and where you are going. Choose a mobility profile: manual chair, power chair, or walker.",
  },
  {
    title: "See both routes",
    body: "ClearCurb draws the plain shortest walk and an accessible route for your profile, with the time and distance of each side by side.",
  },
  {
    title: "Know what was avoided",
    body: "Every barrier the accessible route steers around is listed and marked on the map, with the record it came from.",
  },
];

const BARRIERS = [
  { kind: "missing_ramp", title: "Missing curb ramps", body: "Corners where no ramp could be verified, so a crossing may not be possible at all." },
  { kind: "bad_sidewalk", title: "Broken sidewalks", body: "Open sidewalk violations on the block: trip hazards, broken slabs, and undermined pavement, from DOT records." },
  { kind: "grade", title: "Steep grades", body: "Slopes worked out from surveyed ground elevations, checked against the limit for your profile." },
];

const SOURCES = [
  {
    question: "Where can I walk?",
    name: "LION street centerlines",
    from: "NYC Dept. of City Planning",
    body: "LION knows every street and intersection but has no sidewalks or crosswalks, so we draw a sidewalk along each side of every street and a crossing at every intersection.",
  },
  {
    question: "Can I cross?",
    name: "Pedestrian ramp survey",
    from: "NYC DOT",
    body: "Each end of a crossing is matched to the nearest surveyed curb ramp, carrying its slope, lip height, and warning strip condition onto the crossing.",
  },
  {
    question: "Is the sidewalk in shape?",
    name: "Sidewalk violations",
    from: "NYC DOT, with tax lot data from DOT and City Planning",
    body: "Violations have an address but no coordinates. We follow each one to its tax lot, take the lot's location, and snap it to the street in front of it.",
  },
  {
    question: "Is it too steep?",
    name: "Elevation points",
    from: "NYC Planimetric Database",
    body: "Rooftop points are dropped and ground points are averaged around each corner. The difference between a block's two ends gives its grade.",
  },
];

function RouteSketch() {
  return (
    <svg className="lp-sketch" viewBox="0 0 480 360" role="img" aria-label="Sketch of two routes between the same two points. The dashed standard route goes straight through a missing curb ramp and a broken sidewalk. The solid accessible route detours around both.">
      <rect width="480" height="360" fill="var(--color-neutral-300)" />
      {/* avenues */}
      {[70, 190, 310, 430].map((x) => (
        <rect key={x} x={x - 9} y="0" width="18" height="360" fill="var(--color-neutral-100)" />
      ))}
      {/* cross streets */}
      {[60, 140, 220, 300].map((y) => (
        <rect key={y} x="0" y={y - 5} width="480" height="10" fill="var(--color-neutral-100)" />
      ))}
      {/* standard route */}
      <path d="M70 300 V140 H190 V60 H310" fill="none" stroke="var(--color-text)" strokeWidth="6" strokeDasharray="14 9" />
      {/* accessible route */}
      <path d="M70 300 H190 V220 H310 V60" fill="none" stroke="var(--color-accent)" strokeWidth="8" />
      {/* barriers on the standard route */}
      <circle cx="70" cy="200" r="10" fill="var(--color-accent-700)" stroke="var(--color-bg)" strokeWidth="3" />
      <rect x="182" y="90" width="16" height="16" fill="var(--color-bg)" stroke="var(--color-accent-600)" strokeWidth="4" />
      {/* origin, destination */}
      <circle cx="70" cy="300" r="10" fill="var(--color-bg)" stroke="var(--color-text)" strokeWidth="4" />
      <rect x="298" y="48" width="24" height="24" fill="var(--color-accent)" stroke="var(--color-bg)" strokeWidth="3" />
    </svg>
  );
}

export default function Landing() {
  return (
    <div className="lp">
      <header className="lp-nav">
        <div className="cc-brand lp-brand">
          <span className="cc-wordmark">CLEARCURB</span>
          <span className="cc-chip">NYC</span>
        </div>
        <nav aria-label="Sections">
          <a href="#how">How it works</a>
          <a href="#avoids">What it avoids</a>
          <a href="#data">Data</a>
        </nav>
        <Link href="/plan" className="lp-nav__cta">
          PLAN A ROUTE
        </Link>
      </header>

      <main>
        <section className="lp-hero">
          <div className="lp-hero__copy">
            <span className="cc-label">Accessible route planning · Lower Manhattan</span>
            <h1>The shortest walk is not always one you can take.</h1>
            <p className="lp-lede">
              ClearCurb plans walking routes around missing curb ramps, steep grades, and broken sidewalks, and shows you exactly
              what it steered around and what it cost you in time.
            </p>
            <div className="lp-actions">
              <Link href="/plan" className="lp-btn lp-btn--primary">
                PLAN A ROUTE <ArrowRight size={18} aria-hidden />
              </Link>
              <a href="#how" className="lp-btn">
                HOW IT WORKS
              </a>
            </div>
          </div>
          <figure className="lp-hero__art">
            <RouteSketch />
            <figcaption>
              <span className="lp-key lp-key--standard" /> Standard route
              <span className="lp-key lp-key--accessible" /> Accessible route
            </figcaption>
          </figure>
        </section>

        <section className="lp-facts" aria-label="At a glance">
          <div>
            <strong>2 routes</strong>
            <span>for every trip, compared side by side</span>
          </div>
          <div>
            <strong>3 profiles</strong>
            <span>manual chair, power chair, walker</span>
          </div>
          <div>
            <strong>Open data</strong>
            <span>city surveys, maps, and records</span>
          </div>
        </section>

        <section id="how" className="lp-section">
          <h2 className="lp-section__title">How it works</h2>
          <ol className="lp-steps">
            {STEPS.map((s, i) => (
              <li key={s.title}>
                <span className={`lp-step__n lp-step__n--${i}`}>{i + 1}</span>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="avoids" className="lp-section lp-section--split">
          <h2 className="lp-section__title">What it avoids</h2>
          <ul className="lp-barriers">
            {BARRIERS.map((b) => (
              <li key={b.kind}>
                <span className={`cc-mark cc-mark--${b.kind}`} aria-hidden />
                <div>
                  <h3>{b.title}</h3>
                  <p>{b.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section id="data" className="lp-section lp-section--split">
          <div>
            <h2 className="lp-section__title">Where the data comes from</h2>
            <p className="lp-data__intro">
              No single city dataset says whether a route works for a wheelchair. ClearCurb stitches several open NYC datasets
              onto one sidewalk map, so every barrier on a route traces back to a public record.
            </p>
          </div>
          <ol className="lp-sources">
            {SOURCES.map((s) => (
              <li key={s.name}>
                <span className="cc-label lp-sources__q">{s.question}</span>
                <div>
                  <h3>{s.name}</h3>
                  <span className="lp-sources__from">{s.from}</span>
                  <p>{s.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="lp-final">
          <h2>Try a trip.</h2>
          <Link href="/plan" className="lp-btn lp-btn--inverse">
            PLAN A ROUTE <ArrowRight size={18} aria-hidden />
          </Link>
        </section>
      </main>

      <footer className="lp-footer">
        <span className="cc-label">ClearCurb</span>
        <span>Built on NYC open data.</span>
      </footer>
    </div>
  );
}
