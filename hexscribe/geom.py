import math
from typing import Tuple

def lerp(a, b, t): return (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t)

def perp_unit(a: Tuple[float,float], b: Tuple[float,float]):
    dx, dy = b[0]-a[0], b[1]-a[1]
    L = math.hypot(dx, dy) or 1.0
    return (-dy/L, dx/L)

def dot(a,b): return a[0]*b[0] + a[1]*b[1]
def clamp(v,a,b): return max(a, min(b, v))

def dist2(p,q): return (p[0]-q[0])**2 + (p[1]-q[1])**2

def seg_dist_to_point_sq(a,b,p):
    ap = (p[0]-a[0], p[1]-a[1]); ab = (b[0]-a[0], b[1]-a[1])
    ab2 = ab[0]*ab[0] + ab[1]*ab[1]
    if ab2 == 0: return dist2(a,p)
    t = clamp(dot(ap,ab)/ab2, 0.0, 1.0)
    proj = (a[0]+ab[0]*t, a[1]+ab[1]*t)
    return dist2(proj, p)
