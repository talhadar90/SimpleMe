using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Numerics;
using System.Linq;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;
using SixLabors.ImageSharp.Drawing;
using SixLabors.ImageSharp.Drawing.Processing;
using SixLabors.ImageSharp.Processing;

public static class OrthoProjector
{
    public static void RenderOrthographicPNG(
        IReadOnlyList<TriangleRow> rows,
        Vector3 viewDir,              // e.g., new(0,0,1) means “look along +Z”
        int width, int height,
        int padding,
        string outPngPath,
        Rgba32? background = null)
    {
        if (rows == null || rows.Count == 0) throw new ArgumentException("No triangles.");

        // 1) Build an orthonormal basis (right, up) perpendicular to viewDir
        var v = Vector3.Normalize(viewDir);
        var upHint = MathF.Abs(Vector3.Dot(v, Vector3.UnitY)) > 0.99f ? Vector3.UnitX : Vector3.UnitY;
        var right = Vector3.Normalize(Vector3.Cross(v, upHint));
        var up = Vector3.Normalize(Vector3.Cross(right, v)); // right × v

        // 2) Back-face cull & prepare projected triangles
        var tris = new List<(Vector2 a, Vector2 b, Vector2 c, float depth, Rgba32 color)>(rows.Count);
        tris.Capacity = rows.Count;

        foreach (var t in rows)
        {
            var A3 = new Vector3(t.Ax, t.Ay, t.Az);
            var B3 = new Vector3(t.Bx, t.By, t.Bz);
            var C3 = new Vector3(t.Cx, t.Cy, t.Cz);

            // Normal & facing test (RH coord; keep if facing camera)
            var n = Vector3.Normalize(Vector3.Cross(B3 - A3, C3 - A3));
            var facing = Vector3.Dot(n, v) < 0f; // keep triangles whose normal opposes viewDir
            if (!facing) continue;

            // Orthographic projection onto (right, up) plane
            Vector2 proj(Vector3 p) => new Vector2(Vector3.Dot(p, right), Vector3.Dot(p, up));
            var a2 = proj(A3);
            var b2 = proj(B3);
            var c2 = proj(C3);

            // Depth for painter’s sort (along viewDir)
            float depth = Vector3.Dot((A3 + B3 + C3) / 3f, v);

            // Color (rows r,g,b are in sRGB 0..1)
            var color = new Rgba32(
                (byte)Math.Clamp((int)Math.Round(t.R * 255f), 0, 255),
                (byte)Math.Clamp((int)Math.Round(t.G * 255f), 0, 255),
                (byte)Math.Clamp((int)Math.Round(t.B * 255f), 0, 255),
                255);

            tris.Add((a2, b2, c2, depth, color));
        }

        if (tris.Count == 0)
            throw new InvalidOperationException("No front-facing triangles from this view.");

        // 3) Compute bounds in projected space and scale to image
        float minX = float.PositiveInfinity, minY = float.PositiveInfinity;
        float maxX = float.NegativeInfinity, maxY = float.NegativeInfinity;
        void expand(Vector2 p)
        {
            if (p.X < minX) minX = p.X; if (p.X > maxX) maxX = p.X;
            if (p.Y < minY) minY = p.Y; if (p.Y > maxY) maxY = p.Y;
        }
        foreach (var t in tris) { expand(t.a); expand(t.b); expand(t.c); }

        float spanX = Math.Max(1e-6f, maxX - minX);
        float spanY = Math.Max(1e-6f, maxY - minY);
        float sx = (width - 2f * padding) / spanX;
        float sy = (height - 2f * padding) / spanY;
        float scale = MathF.Min(sx, sy);

        Vector2 toPx(Vector2 p)
        {
            float x = (p.X - minX) * scale + padding;
            float y = (p.Y - minY) * scale + padding;
            // Flip Y to top-left origin
            y = height - y;
            return new Vector2(x, y);
        }

        // 4) Sort far → near (painter’s algorithm)
        tris.Sort((t1, t2) => t2.depth.CompareTo(t1.depth));

        // 5) Rasterize to PNG
        var bg = background ?? new Rgba32(0, 0, 0, 0);
        using var img = new Image<Rgba32>(width, height, bg);

        foreach (var t in tris)
        {
            var pa = toPx(t.a);
            var pb = toPx(t.b);
            var pc = toPx(t.c);

            var path = new PathBuilder();
            path.AddLines(new PointF[] {
                new PointF(pa.X, pa.Y),
                new PointF(pb.X, pb.Y),
                new PointF(pc.X, pc.Y)
            });
            path.CloseFigure();

            img.Mutate(ctx =>
            {
                // Anti-aliased fill; no stroke
                ctx.Fill(t.color, path.Build());
            });
        }

        img.SaveAsPng(outPngPath);
    }
}
