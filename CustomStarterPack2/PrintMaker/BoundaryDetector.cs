using SixLabors.ImageSharp.Drawing.Processing;
using SixLabors.ImageSharp.PixelFormats;
using SixLabors.ImageSharp;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using SixLabors.ImageSharp.Processing;

static class BoundaryDetector
{
    public record BoundaryInfo(
        int Id,
        bool IsHole,
        List<Point> BoundaryPixels,
        Rectangle BBox,
        int AreaPixels,
        (double X, double Y) MedianXY
    );
    private static bool[,] BuildSolidMask(Image<Rgba32> img, byte alphaThreshold)
    {
        int W = img.Width, H = img.Height;
        var solid = new bool[W, H];

        img.ProcessPixelRows(accessor =>
        {
            for (int y = 0; y < H; y++)
            {
                var row = accessor.GetRowSpan(y);
                for (int x = 0; x < W; x++)
                    solid[x, y] = row[x].A >= alphaThreshold;
            }
        });

        return solid;
    }
    public static List<BoundaryInfo> DetectBoundaries(Image<Rgba32> img, byte alphaThreshold = 1)
    {
        int W = img.Width, H = img.Height;
        bool[,] solid = BuildSolidMask(img, alphaThreshold);


        var results = new List<BoundaryInfo>();

        // --- Foreground components (solid == true) ---
        var seenF = new bool[W, H];
        int id = 1;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++)
            {
                if (solid[x, y] && !seenF[x, y])
                {
                    var comp = FloodCollect(solid, x, y, wantTrue: true, seenF);
                    var boundary = ExtractBoundary(comp, solid, wantTrue: true, W, H);
                    var bbox = ComputeBBox(comp);
                    var median = Median(comp);
                    results.Add(new BoundaryInfo(id++, false, boundary, bbox, comp.Count, median));
                }
            }

        // --- Background components fully enclosed (holes): solid == false not touching edges ---
        var seenB = new bool[W, H];
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++)
            {
                if (!solid[x, y] && !seenB[x, y])
                {
                    var comp = FloodCollect(solid, x, y, wantTrue: false, seenB);
                    bool touchesEdge = comp.Exists(p => p.X == 0 || p.Y == 0 || p.X == W - 1 || p.Y == H - 1);
                    if (!touchesEdge)
                    {
                        var boundary = ExtractBoundary(comp, solid, wantTrue: false, W, H);
                        var bbox = ComputeBBox(comp);
                        var median = Median(comp);
                        results.Add(new BoundaryInfo(id++, true, boundary, bbox, comp.Count, median));
                    }
                }
            }

        return results;
    }

    public static void PrintSummary(List<BoundaryInfo> infos)
    {
        Console.WriteLine($"[BOUNDARIES] Found {infos.Count} boundaries (foreground + holes).");
        foreach (var b in infos)
        {
            Console.WriteLine(
                $"  • ID {b.Id} | {(b.IsHole ? "HOLE" : "OBJECT")} | " +
                $"Area(px): {b.AreaPixels} | Boundary(px): {b.BoundaryPixels.Count} | " +
                $"BBox: [{b.BBox.X},{b.BBox.Y} {b.BBox.Width}x{b.BBox.Height}] | " +
                $"Median: ({b.MedianXY.X:0.0}, {b.MedianXY.Y:0.0})"
            );
        }
    }

    // ---------- internals ----------

    private static List<Point> FloodCollect(bool[,] solid, int sx, int sy, bool wantTrue, bool[,] seen)
    {
        int W = solid.GetLength(0), H = solid.GetLength(1);
        var comp = new List<Point>(1024);
        var q = new Queue<Point>();
        seen[sx, sy] = true;
        q.Enqueue(new Point(sx, sy));

        // 8-connectivity for robust component grouping
        ReadOnlySpan<(int dx, int dy)> nb = stackalloc (int, int)[]
        {
            (-1, -1), (0, -1), (1, -1),
            (-1,  0),          (1,  0),
            (-1,  1), (0,  1), (1,  1),
        };

        while (q.Count > 0)
        {
            var p = q.Dequeue();
            comp.Add(p);
            foreach (var (dx, dy) in nb)
            {
                int nx = p.X + dx, ny = p.Y + dy;
                if ((uint)nx >= (uint)W || (uint)ny >= (uint)H) continue;
                if (seen[nx, ny]) continue;
                if (solid[nx, ny] == wantTrue)
                {
                    seen[nx, ny] = true;
                    q.Enqueue(new Point(nx, ny));
                }
            }
        }
        return comp;
    }

    private static List<Point> ExtractBoundary(List<Point> comp, bool[,] solid, bool wantTrue, int W, int H)
    {
        var boundary = new List<Point>(comp.Count / 4 + 8);
        // 4-neighborhood is enough to decide "edge"
        ReadOnlySpan<(int dx, int dy)> nb4 = stackalloc (int, int)[]
        {
            (0,-1), (-1,0), (1,0), (0,1)
        };

        foreach (var p in comp)
        {
            bool isEdge = false;
            foreach (var (dx, dy) in nb4)
            {
                int nx = p.X + dx, ny = p.Y + dy;
                if ((uint)nx >= (uint)W || (uint)ny >= (uint)H)
                {
                    isEdge = true; break;
                }
                if (solid[nx, ny] != wantTrue)
                {
                    isEdge = true; break;
                }
            }
            if (isEdge) boundary.Add(p);
        }
        return boundary;
    }

    private static Rectangle ComputeBBox(List<Point> pts)
    {
        int minX = int.MaxValue, minY = int.MaxValue;
        int maxX = int.MinValue, maxY = int.MinValue;
        foreach (var p in pts)
        {
            if (p.X < minX) minX = p.X;
            if (p.Y < minY) minY = p.Y;
            if (p.X > maxX) maxX = p.X;
            if (p.Y > maxY) maxY = p.Y;
        }
        return new Rectangle(minX, minY, Math.Max(1, maxX - minX + 1), Math.Max(1, maxY - minY + 1));
    }

    private static (double X, double Y) Median(List<Point> pts)
    {
        // Median is more robust than mean; compute per-axis
        var xs = new int[pts.Count];
        var ys = new int[pts.Count];
        for (int i = 0; i < pts.Count; i++) { xs[i] = pts[i].X; ys[i] = pts[i].Y; }
        Array.Sort(xs); Array.Sort(ys);
        double medX = xs.Length % 2 == 1 ? xs[xs.Length / 2] : 0.5 * (xs[xs.Length / 2 - 1] + xs[xs.Length / 2]);
        double medY = ys.Length % 2 == 1 ? ys[ys.Length / 2] : 0.5 * (ys[ys.Length / 2 - 1] + ys[ys.Length / 2]);
        return (medX, medY);
    }

    // Color all boundary pixels (foreground + holes) with a single color.
    // thickness = 1 paints a single pixel; >1 paints a square kernel of side = thickness.
    public static void PaintBoundaries(Image<Rgba32> img, List<BoundaryInfo> infos, Rgba32 color, int thickness = 1)
    {
        int W = img.Width, H = img.Height;
        int r = Math.Max(0, (thickness - 1) / 2);

        img.ProcessPixelRows(accessor =>
        {
            foreach (var b in infos)
            {
                foreach (var p in b.BoundaryPixels)
                {
                    for (int dy = -r; dy <= r; dy++)
                    {
                        int y = p.Y + dy;
                        if ((uint)y >= (uint)H) continue;
                        var row = accessor.GetRowSpan(y);
                        for (int dx = -r; dx <= r; dx++)
                        {
                            int x = p.X + dx;
                            if ((uint)x >= (uint)W) continue;
                            row[x] = color;
                        }
                    }
                }
            }
        });
    }// Draw anti-aliased straight-line contours instead of per-pixel dots.
     // thickness in pixels; set closeLoops=false to leave contours open.
    public static void PaintBoundaryAA(Image<Rgba32> img, BoundaryInfo b, Rgba32 color, float thickness = 1f, bool closeLoops = true)
    {
        var opts = new DrawingOptions
        {
            GraphicsOptions = new GraphicsOptions { Antialias = true }
        };
        var pen = Pens.Solid(color, thickness);

        img.Mutate(ctx =>
        {
            // Ensure an ordered path; if you've already called SmoothAllBoundaries, it’s ordered.
            var pts = b.BoundaryPixels;

            if (pts.Count < 2) return;

            // Convert to PointF[]
            var poly = new PointF[closeLoops ? pts.Count + 1 : pts.Count];
            for (int i = 0; i < pts.Count; i++)
                poly[i] = new PointF(pts[i].X, pts[i].Y);
            if (closeLoops)
                poly[^1] = poly[0];

            ctx.DrawLine(opts, pen, poly);
        });
    }

    // Overload to color objects vs holes differently.
    public static void PaintBoundariesAA(Image<Rgba32> img, List<BoundaryInfo> infos, Rgba32 objectColor, Rgba32 holeColor, float thickness = 1f, bool closeLoops = true)
    {
        var opts = new DrawingOptions
        {
            GraphicsOptions = new GraphicsOptions { Antialias = true }
        };

        img.Mutate(ctx =>
        {
            foreach (var b in infos)
            {
                var pts = b.BoundaryPixels;
                if (pts.Count < 2) continue;

                var pen = Pens.Solid(b.IsHole ? holeColor : objectColor, thickness);

                var poly = new PointF[closeLoops ? pts.Count + 1 : pts.Count];
                for (int i = 0; i < pts.Count; i++)
                    poly[i] = new PointF(pts[i].X, pts[i].Y);
                if (closeLoops)
                    poly[^1] = poly[0];

                ctx.DrawLine(opts, pen, poly);
            }
        });
    }

    // Variant: paint objects and holes with different colors for quick visual separation.
    public static void PaintBoundaries(Image<Rgba32> img, List<BoundaryInfo> infos, Rgba32 objectColor, Rgba32 holeColor, int thickness = 1)
    {
        int W = img.Width, H = img.Height;
        int r = Math.Max(0, (thickness - 1) / 2);

        img.ProcessPixelRows(accessor =>
        {
            foreach (var b in infos)
            {
                var color = b.IsHole ? holeColor : objectColor;
                foreach (var p in b.BoundaryPixels)
                {
                    for (int dy = -r; dy <= r; dy++)
                    {
                        int y = p.Y + dy;
                        if ((uint)y >= (uint)H) continue;
                        var row = accessor.GetRowSpan(y);
                        for (int dx = -r; dx <= r; dx++)
                        {
                            int x = p.X + dx;
                            if ((uint)x >= (uint)W) continue;
                            row[x] = color;
                        }
                    }
                }
            }
        });
    }

    // ======= BOUNDARY SMOOTHING =======

    // Smooth all boundaries in-place (objects + holes).
    // iterations: how many passes of smoothing to run (>=1)
    // window: odd size of the moving average window, typically 3 or 5
    public static void SmoothBoundary(BoundaryInfo b, int iterations = 3, int window = 3, bool assumeClosed = true)
    {
        var smoothed = SmoothContour(b.BoundaryPixels, iterations, window, assumeClosed);

        b.BoundaryPixels.Clear();
        b.BoundaryPixels.AddRange(smoothed);
    }
    // Moving-average smoothing along the ordered contour.
    // Uses wrap-around if assumeClosed = true.
    private static List<Point> SmoothContour(List<Point> ordered, int iterations, int window, bool assumeClosed)
    {
        if (ordered.Count == 0) return ordered;
        if (window < 3 || window % 2 == 0) window = 3;  // enforce odd >= 3

        var pts = ordered.Select(p => new System.Numerics.Vector2(p.X, p.Y)).ToArray();
        var tmp = new System.Numerics.Vector2[pts.Length];
        int n = pts.Length;
        int r = window / 2;

        for (int it = 0; it < iterations; it++)
        {
            for (int i = 0; i < n; i++)
            {
                int i0 = i - r, i1 = i + r;
                System.Numerics.Vector2 acc = default;
                int count = 0;

                for (int k = i0; k <= i1; k++)
                {
                    int idx;
                    if (assumeClosed)
                    {
                        idx = (k % n + n) % n; // wrap
                    }
                    else
                    {
                        if (k < 0 || k >= n) continue; // clamp by skipping
                        idx = k;
                    }
                    acc += pts[idx];
                    count++;
                }
                tmp[i] = acc / Math.Max(1, count);
            }

            // swap
            var swap = pts; pts = tmp; tmp = swap;
        }

        // Quantize back to pixels; also remove consecutive duplicates
        var outList = new List<Point>(n);
        Point? last = null;
        for (int i = 0; i < n; i++)
        {
            var qx = (int)Math.Round(pts[i].X);
            var qy = (int)Math.Round(pts[i].Y);
            var cur = new Point(qx, qy);
            if (last == null || cur != last.Value)
            {
                outList.Add(cur);
                last = cur;
            }
        }
        // Optional: if closed and last == first, drop the last duplicate
        if (assumeClosed && outList.Count > 1 && outList[0] == outList[^1])
            outList.RemoveAt(outList.Count - 1);

        return outList;
    }
    // Trim the ordered contour after it "closes" back near the start.
    // - warmup: number of initial points to scan to set the reference max distance from p0
    // - factor: closure threshold as a fraction of that max (e.g., 0.95 -> "closer than 95% of farthest")
    // - closeLoop: if true, append the start point at the end (for drawing closed loops)
    public static void TrimAfterClosureByDistance(BoundaryInfo b, int warmup = 50, double factor = 0.95, bool closeLoop = true)
    {
        var ordered = b.BoundaryPixels;
        if (ordered == null || ordered.Count < 4) return;

        var p0 = ordered[0];

        
        // 2) Find first point after warmup that is "close enough" back to p0
        for (int i = warmup + 1; i < ordered.Count; i++)
        {
            long d2 = Dist2(p0, ordered[i]);
            if (d2 <= 2 && i > ordered.Count / 2)
            {
                // Keep up to and including this point; drop the rest
                int keep = i + 1;
                if (keep < ordered.Count)
                    ordered.RemoveRange(keep, ordered.Count - keep);

                if (closeLoop)
                {
                    if (ordered[^1] != p0)
                        ordered.Add(p0);
                }
                return;
            }
        }
        // If no closure was detected, leave list as-is.
    }

    private static long Dist2(Point a, Point b)
    {
        long dx = (long)b.X - a.X;
        long dy = (long)b.Y - a.Y;
        return dx * dx + dy * dy;
    }

    // Greedy nearest-neighbor ordering to turn an unordered boundary set into a path.
    // O(n^2) but fine for typical boundary sizes. Produces a closed loop if endpoints meet.
    public static void OrderContourGreedy(BoundaryInfo b)
    {
        var unordered = b.BoundaryPixels;
        if (unordered.Count <= 2) return;

        // Start from the lexicographically smallest (x+y) to anchor deterministically
        int startIdx = 0;
        int bestKey = unordered[0].X + unordered[0].Y;
        for (int i = 1; i < unordered.Count; i++)
        {
            int key = unordered[i].X + unordered[i].Y;
            if (key < bestKey) { bestKey = key; startIdx = i; }
        }

        var used = new bool[unordered.Count];
        var ordered = new List<Point>(unordered.Count);
        int cur = startIdx;
        used[cur] = true;
        ordered.Add(unordered[cur]);

        for (; ; )
        {
            int best = -1;
            int bestD2 = int.MaxValue;

            var c = unordered[cur];
            for (int j = 0; j < unordered.Count; j++)
            {
                if (used[j]) continue;
                var p = unordered[j];
                int dx = p.X - c.X, dy = p.Y - c.Y;
                int d2 = dx * dx + dy * dy;
                if (d2 < bestD2)
                {
                    bestD2 = d2; best = j;
                }
            }
            if (best == -1) break;
            used[best] = true;
            ordered.Add(unordered[best]);
            cur = best;
        }
        unordered.Clear();
        unordered.AddRange(ordered);
    }// Prefer Moore-Neighbor tracing for a clean, non-crossing ordered contour.
     // Build the mask once, then trace each boundary using a left-hand rule.
    public static void OrderAllContoursMoore(Image<Rgba32> img, List<BoundaryInfo> infos, byte alphaThreshold = 1)
    {
        int W = img.Width, H = img.Height;
        var solid = BuildSolidMask(img, alphaThreshold);

        foreach (var info in infos)
        {
            if (info.BoundaryPixels.Count < 2) continue;

            // Pick deterministic start: top-most, then left-most boundary pixel
            var start = info.BoundaryPixels
                .OrderBy(p => p.Y).ThenBy(p => p.X)
                .First();

            var ordered = TraceContourMoore(solid, W, H, wantTrue: !info.IsHole, start);

            if (ordered.Count >= 2)
            {
                info.BoundaryPixels.Clear();
                info.BoundaryPixels.AddRange(ordered);
            }
            // else keep the original set as fallback
        }
    }

    // 8-neighborhood (clockwise)
    static readonly (int dx, int dy)[] NB8 =
    {
    ( 1, 0), ( 1, 1), ( 0, 1), (-1, 1),
    (-1, 0), (-1,-1), ( 0,-1), ( 1,-1)
};

    public static BoundaryInfo MakeRoundedRectBoundary(int id, int width, int height, float radiusPx, int cornerSegments = 12)
    {
        // Clamp radius
        float r = MathF.Max(0f, MathF.Min(radiusPx, MathF.Min((width - 1) * 0.5f, (height - 1) * 0.5f)));

        // Corner centers
        float cxTL = r, cyTL = r;
        float cxTR = (width - 1) - r, cyTR = r;
        float cxBR = (width - 1) - r, cyBR = (height - 1) - r;
        float cxBL = r, cyBL = (height - 1) - r;

        // Helper to add arc points (inclusive end)
        void AddArc(List<Point> pts, float cx, float cy, float startDeg, float endDeg, int segs)
        {
            double s = startDeg * Math.PI / 180.0;
            double e = endDeg * Math.PI / 180.0;
            int n = Math.Max(1, segs);
            for (int i = 0; i <= n; i++)
            {
                double t = s + (e - s) * (i / (double)n);
                int x = (int)Math.Round(cx + r * Math.Cos(t));
                int y = (int)Math.Round(cy + r * Math.Sin(t));
                if (pts.Count == 0 || pts[^1].X != x || pts[^1].Y != y)
                    pts.Add(new Point(x, y));
            }
        }

        var poly = new List<Point>(4 * (cornerSegments + 1));

        if (r <= 0.5f)
        {
            // Plain rectangle border (clockwise)
            poly.Add(new Point(0, 0));
            poly.Add(new Point(width - 1, 0));
            poly.Add(new Point(width - 1, height - 1));
            poly.Add(new Point(0, height - 1));
        }
        else
        {
            // Clockwise: TL arc (180→270), TR (270→360), BR (0→90), BL (90→180)
            AddArc(poly, cxTL, cyTL, 180f, 270f, cornerSegments);
            AddArc(poly, cxTR, cyTR, 270f, 360f, cornerSegments);
            AddArc(poly, cxBR, cyBR, 0f, 90f, cornerSegments);
            AddArc(poly, cxBL, cyBL, 90f, 180f, cornerSegments);
        }

        // Build BoundaryInfo (bbox/area/median are straightforward)
        var bbox = new Rectangle(0, 0, width, height);
        int area = width * height;
        var median = new Point(width / 2, height / 2);

        // isHole = false (it’s an outer contour)
        return new BoundaryInfo(id, /*isHole*/ false, poly, bbox, area, (median.X, median.Y));
    }
    // Moore-Neighbor border following.
    // wantTrue=true traces a foreground object border; false traces a hole (background island).
    private static List<Point> TraceContourMoore(bool[,] solid, int W, int H, bool wantTrue, Point start)
    {
        var contour = new List<Point>(512);
        // Find starting backtrack neighbor: pick the neighbor to the "west" of start (index 4: (-1,0))
        int backIdx = 4;
        var p = start;

        // Find first neighbor around start
        int firstDir = -1;
        for (int k = 0; k < 8; k++)
        {
            int idx = (backIdx + 1 + k) % 8; // clockwise search starting one step after back
            int nx = p.X + NB8[idx].dx;
            int ny = p.Y + NB8[idx].dy;
            if ((uint)nx < (uint)W && (uint)ny < (uint)H && solid[nx, ny] == wantTrue)
            {
                firstDir = idx;
                break;
            }
        }
        if (firstDir == -1)
        {
            // Edge case: isolated single pixel
            contour.Add(start);
            return contour;
        }

        // Start loop
        contour.Add(p);
        var prevDir = firstDir; // direction from p to next
        p = new Point(p.X + NB8[prevDir].dx, p.Y + NB8[prevDir].dy);
        contour.Add(p);

        // Backtrack direction is the opposite of prevDir
        int backFromPrev = (prevDir + 4) % 8;

        // Termination condition: return to start with same successor
        var start2 = contour[1];
        int safety = W * H * 4; // robust guard
        while (safety-- > 0)
        {
            // From current p, search clockwise starting one step after backtrack neighbor
            int foundDir = -1;
            for (int k = 0; k < 8; k++)
            {
                int idx = (backFromPrev + 1 + k) % 8;
                int nx = p.X + NB8[idx].dx;
                int ny = p.Y + NB8[idx].dy;
                if ((uint)nx < (uint)W && (uint)ny < (uint)H && solid[nx, ny] == wantTrue)
                {
                    foundDir = idx;
                    break;
                }
            }

            if (foundDir == -1)
            {
                // Shouldn't happen for a proper boundary; stop to avoid infinite loop
                break;
            }

            // Advance
            var nextP = new Point(p.X + NB8[foundDir].dx, p.Y + NB8[foundDir].dy);
            contour.Add(nextP);

            // Check closing: last segment brought us back to start with same next
            if (nextP == start && p == start2)
                break;

            // Prepare next iteration
            backFromPrev = (foundDir + 4) % 8;
            p = nextP;
        }

        // Remove a duplicated last point if present
        if (contour.Count > 1 && contour[0] == contour[^1])
            contour.RemoveAt(contour.Count - 1);

        return contour;
    }

}