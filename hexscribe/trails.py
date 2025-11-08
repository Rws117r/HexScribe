import math, heapq, random
from typing import List, Tuple, Dict, Set
from PIL import ImageDraw
from .hexgrid import HexGrid

# keep spacing between trails so they don't pile up
NO_OVERLAP_DIST = 14  # px

def _perp_unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    return (-dy / L, dx / L)

def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


class TrailRouter:
    """
    Routes trails using A* over the hex graph (from HexGrid).
    Diamonds are solid obstacles (except the two endpoints being connected).
    Styles:
      - path      : plain stroke
      - difficult : cross-ties
      - dangerous : chevron barbs
      - special   : dashed line (8/6)
    """
    def __init__(self):
        self.samples_log: List[Tuple[str, List[Tuple[float, float]]]] = []
        self.used_edges: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()

    # ---------- style picker ----------
    def _style(self) -> str:
        r = random.randint(1, 8)
        if   1 <= r <= 4: return "path"
        elif 5 <= r <= 6: return "difficult"
        elif r == 7:      return "dangerous"
        else:             return "special"

    # ---------- grid helpers ----------
    def _closest_node(self, grid: HexGrid, x: int, y: int) -> Tuple[int, int]:
        best, bd = None, 10**9
        for n in grid.nodes:
            d2 = (n['x'] - x) ** 2 + (n['y'] - y) ** 2
            if d2 < bd:
                bd = d2
                best = (n['q'], n['r'])
        return best

    def _edge_key(self, a: Tuple[int, int], b: Tuple[int, int]):
        return tuple(sorted([a, b]))

    # ---------- A* ----------
    def _astar(self, grid: HexGrid,
               start: Tuple[int, int], goal: Tuple[int, int],
               blocked: Set[Tuple[int, int]]) -> List[Tuple[int, int]]:

        def h(p):
            (q1, r1), (q2, r2) = p, goal
            # hex distance
            return (abs(q1 - q2) + abs((q1 + r1) - (q2 + r2)) + abs(r1 - r2)) / 2

        openq = [(0.0, start)]
        came: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g = {start: 0.0}

        while openq:
            _, cur = heapq.heappop(openq)
            if cur == goal:
                path = [cur]
                while cur in came:
                    cur = came[cur]
                    path.append(cur)
                return list(reversed(path))

            for nbr in grid.neighbors(*cur):
                if nbr in blocked:
                    continue
                step = 1.0
                # discourage reusing the same corridor
                if self._edge_key(cur, nbr) in self.used_edges:
                    step += 2.0
                step += random.uniform(0.0, 0.25)  # variety

                ng = g[cur] + step
                if ng < g.get(nbr, 1e9):
                    g[nbr] = ng
                    heapq.heappush(openq, (ng + h(nbr), nbr))
                    came[nbr] = cur
        return []

    # ---------- polyline helpers ----------
    def _poly_from_axial(self, grid: HexGrid, path_ax: List[Tuple[int, int]]):
        return [(float(grid.node_lookup[(q, r)][0]),
                 float(grid.node_lookup[(q, r)][1])) for q, r in path_ax]

    def _trim_to_diamond_edge(self, center, toward, radius_px):
        ax, ay = center; bx, by = toward
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        return (ax + ux * (radius_px + 2), ay + uy * (radius_px + 2))

    def _chaikin(self, pts, iters=2):
        """Chaikin corner-cutting; preserves endpoints."""
        if len(pts) < 3:
            return pts[:]
        out = pts[:]
        for _ in range(iters):
            newp = [out[0]]
            for i in range(len(out) - 1):
                a, b = out[i], out[i + 1]
                q = (0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1])
                r = (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])
                newp.extend([q, r])
            newp.append(out[-1])
            out = newp
        return out

    def _evenly_sample(self, pts, step=3.5):
        """Resample polyline roughly every 'step' px for consistent ornament spacing."""
        if len(pts) < 2:
            return pts[:]
        acc = [pts[0]]
        carry = 0.0
        for i in range(len(pts) - 1):
            a = acc[-1]; b = pts[i + 1]
            seg = _dist(a, b)
            if seg <= 1e-6:
                continue
            dirx = (b[0] - a[0]) / seg; diry = (b[1] - a[1]) / seg
            t = step - carry
            while t <= seg:
                acc.append((a[0] + dirx * t, a[1] + diry * t))
                t += step
            carry = seg - (t - step)
            acc[-1] = (b[0], b[1])
        return acc

    # ---------- drawing with avoidance ----------
    def _stroke(self, d: ImageDraw.ImageDraw, pts, style: str,
                avoid_circles: List[Tuple[int, int, float]]):

        # main stroke
        d.line(pts, fill=0, width=2)

        def _near_any_circle(p, pad=0.0):
            x, y = p
            for cx, cy, r in avoid_circles:
                if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= (r + pad) * (r + pad):
                    return True
            return False

        def _safe_positions(step_pts, edge_clear=10.0):
            safe = []
            for i in range(1, len(step_pts) - 1):
                c = step_pts[i]
                if _near_any_circle(c, pad=4.0):
                    continue
                if _dist(c, pts[0]) < edge_clear or _dist(c, pts[-1]) < edge_clear:
                    continue
                safe.append((i, c))
            return safe

        if style == "difficult":
            step_pts = self._evenly_sample(pts, step=10)
            for i, c in _safe_positions(step_pts):
                p = step_pts[i - 1]; q = step_pts[i + 1]
                nx, ny = _perp_unit(p, q); tick = 5
                d.line([(c[0] - nx * tick, c[1] - ny * tick),
                        (c[0] + nx * tick, c[1] + ny * tick)], fill=0, width=2)

        elif style == "dangerous":
            step_pts = self._evenly_sample(pts, step=14)
            for i, c in _safe_positions(step_pts):
                p = step_pts[i - 1]; q = step_pts[i + 1]
                nx, ny = _perp_unit(p, q)
                dx, dy = q[0] - p[0], q[1] - p[1]
                L = math.hypot(dx, dy) or 1.0
                ux, uy = dx / L, dy / L
                barb = 6
                left  = (c[0] - ux * barb + nx * barb, c[1] - uy * barb + ny * barb)
                right = (c[0] - ux * barb - nx * barb, c[1] - uy * barb - ny * barb)
                if not (_near_any_circle(left, 4.0) or _near_any_circle(right, 4.0)):
                    d.line([left, c, right], fill=0, width=2)

        elif style == "special":
            # dashed stroke: 8px dash / 6px gap, skipping near diamonds/endpoints
            dash_len, gap = 8.0, 6.0
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                seg_len = _dist(a, b)
                if seg_len <= 1e-6:
                    continue
                ux = (b[0] - a[0]) / seg_len
                uy = (b[1] - a[1]) / seg_len
                pos = 0.0
                draw_dash = True
                while pos < seg_len:
                    s = (a[0] + ux * pos, a[1] + uy * pos)
                    epos = min(seg_len, pos + dash_len)
                    e = (a[0] + ux * epos, a[1] + uy * epos)
                    mid = ((s[0] + e[0]) / 2, (s[1] + e[1]) / 2)
                    near_end = _dist(mid, pts[0]) < 10.0 or _dist(mid, pts[-1]) < 10.0
                    if draw_dash and not near_end:
                        if not any((mid[0] - cx) ** 2 + (mid[1] - cy) ** 2 <= (r + 4.0) ** 2
                                   for cx, cy, r in avoid_circles):
                            d.line([s, e], fill=0, width=2)
                    pos += dash_len + gap
                    draw_dash = not draw_dash

    # ---------- public API ----------
    def draw_trails(self,
                    d: ImageDraw.ImageDraw,
                    diamond_centers: List[Tuple[int, int]],
                    diamond_radius: float,
                    max_trails: int = 4):
        """
        Route up to max_trails trails strictly between diamonds, avoiding
        other diamonds and reusing edges only when needed.
        """
        if len(diamond_centers) < 2:
            return
        if not hasattr(self, "_grid_ref"):
            raise RuntimeError("TrailRouter.draw_trails requires renderer to set _grid_ref to HexGrid")

        grid: HexGrid = self._grid_ref

        # map diamonds to axial nodes
        diamonds_ax = [self._closest_node(grid, x, y) for (x, y) in diamond_centers]

        # choose connections
        pts = diamonds_ax[:]
        random.shuffle(pts)
        upper = min(max_trails, len(pts) - 1)
        segs = 2 if upper >= 2 else upper
        if upper > 2:
            segs = random.randint(2, upper)

        # obstacles: all diamonds except endpoints
        all_blocked = set(diamonds_ax)
        avoid_circles = [(x, y, diamond_radius + 2) for (x, y) in diamond_centers]

        existing_samples: List[Tuple[float, float]] = []

        for i in range(segs):
            a = pts[i]; b = pts[i + 1]
            style = self._style()

            blocked = set(all_blocked)
            blocked.discard(a); blocked.discard(b)

            path_ax = self._astar(grid, a, b, blocked)
            if not path_ax or len(path_ax) < 2:
                continue

            # baseline through centers
            poly = self._poly_from_axial(grid, path_ax)

            # smooth corners
            poly = self._chaikin(poly, iters=2)

            # trim to diamond edges after smoothing
            poly[0]  = self._trim_to_diamond_edge(poly[0],  poly[1],  diamond_radius)
            poly[-1] = self._trim_to_diamond_edge(poly[-1], poly[-2], diamond_radius)

            # spacing guard vs other trails
            if existing_samples:
                md2 = NO_OVERLAP_DIST ** 2
                ok = True
                for (x, y) in poly:
                    for (ex, ey) in existing_samples:
                        if (x - ex) ** 2 + (y - ey) ** 2 < md2:
                            ok = False; break
                    if not ok: break
                if not ok:
                    continue

            # draw with style & avoidance
            self._stroke(d, poly, style, avoid_circles)
            existing_samples.extend(poly)

            # penalize corridor reuse
            for u, v in zip(path_ax[:-1], path_ax[1:]):
                self.used_edges.add(self._edge_key(u, v))

            self.samples_log.append((style, poly))
