/**
 * Verlet rope: N points, both ends pinned, distance constraints between
 * neighbors, gravity, per-hang weights that pull the rope down, and an
 * optional dragged point. Produces an SVG path. Runs 60fps trivially.
 */

export interface RopePoint {
  x: number;
  y: number;
  px: number;
  py: number;
  pinned: boolean;
}

const ITER = 8; // constraint relaxation passes per step
const DAMPING = 0.985;

export class RopeSim {
  points: RopePoint[] = [];
  readonly n: number;
  private segLen: number;

  private restY = 20;

  constructor(width: number, n = 30, baseY = 20) {
    this.restY = baseY;
    this.n = n;
    this.segLen = width / (n - 1);
    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * width;
      const y = baseY;
      this.points.push({ x, y, px: x, py: y, pinned: i === 0 || i === n - 1 });
    }
  }

  resize(width: number) {
    this.segLen = width / (this.n - 1);
    // re-anchor horizontally, keep current shape roughly
    for (let i = 0; i < this.n; i++) {
      const x = (i / (this.n - 1)) * width;
      const dx = x - this.points[i].x;
      this.points[i].x = x;
      this.points[i].px += dx;
    }
  }

  /** One physics step. weights: rope point index → downward force. */
  step(gravity: number, weights: Map<number, number>, drag?: { index: number; x: number; y: number }) {
    // verlet integrate (+ stiffness pull back to the rest line)
    const STIFF = 0.045;
    for (let i = 0; i < this.n; i++) {
      const p = this.points[i];
      if (p.pinned) continue;
      const vx = (p.x - p.px) * DAMPING;
      const vy = (p.y - p.py) * DAMPING;
      p.px = p.x;
      p.py = p.y;
      p.x += vx;
      p.y += vy + gravity + (this.restY - p.y) * STIFF;
    }
    // hanging weights pull their points down
    for (const [i, w] of weights) {
      const p = this.points[i];
      if (!p.pinned) p.y += w;
    }
    // dragged point follows the pointer exactly (stores velocity for snap-back)
    if (drag) {
      const p = this.points[drag.index];
      if (p && !p.pinned) {
        p.px = p.x;
        p.py = p.y;
        p.x = drag.x;
        p.y = drag.y;
      }
    }
    // distance constraints
    for (let k = 0; k < ITER; k++) {
      for (let i = 0; i < this.n - 1; i++) {
        const a = this.points[i];
        const b = this.points[i + 1];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.0001;
        const diff = (dist - this.segLen) / dist / 2;
        if (!a.pinned) {
          a.x += dx * diff;
          a.y += dy * diff;
        }
        if (!b.pinned) {
          b.x -= dx * diff;
          b.y -= dy * diff;
        }
      }
      if (drag) {
        const p = this.points[drag.index];
        if (p && !p.pinned) {
          p.x = drag.x;
          p.y = drag.y;
        }
      }
    }
  }

  /** Nearest rope index for a viewport x. */
  indexAt(x: number, width: number): number {
    const i = Math.round((x / width) * (this.n - 1));
    return Math.max(1, Math.min(this.n - 2, i));
  }

  yAt(index: number): number {
    return this.points[Math.max(0, Math.min(this.n - 1, index))].y;
  }

  /** Downward kick at a point (fresh card lands on the line). */
  impulse(index: number, dy = 14) {
    for (const off of [-1, 0, 1]) {
      const p = this.points[Math.max(0, Math.min(this.n - 1, index + off))];
      if (!p.pinned) {
        p.py = p.y - dy * (off === 0 ? 1 : 0.5); // upward old-pos ⇒ downward velocity
      }
    }
  }

  /** Smooth SVG path through all points (Catmull-Rom-ish via midpoints). */
  path(): string {
    const pts = this.points;
    let d = `M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const xc = (pts[i].x + pts[i + 1].x) / 2;
      const yc = (pts[i].y + pts[i + 1].y) / 2;
      d += ` Q${pts[i].x.toFixed(1)},${pts[i].y.toFixed(1)} ${xc.toFixed(1)},${yc.toFixed(1)}`;
    }
    const last = pts[pts.length - 1];
    d += ` L${last.x.toFixed(1)},${last.y.toFixed(1)}`;
    return d;
  }
}
