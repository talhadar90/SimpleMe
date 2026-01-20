using System.Numerics;
using SharpGLTF.Schema2;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;
using Image = SixLabors.ImageSharp.Image;

public record TriangleRow(
    int MeshIndex, int TriIndex,
    float Ax, float Ay, float Az,
    float Bx, float By, float Bz,
    float Cx, float Cy, float Cz,
    float R, float G, float B
);
public record EdgeRow(
    TriangleRow parentTriangle,
    float Ax, float Ay,
    float Bx, float By,
    float R, float G, float B
);

public static class GlbDiffuseAnalyzer
{
    public static List<TriangleRow> Analyze(string glbPath, int samplesPerTri = 16)
    {
        var model = ModelRoot.Load(glbPath);
        var rows = new List<TriangleRow>();
        int meshCounter = 0;

        // Preload texture images into ImageSharp by texture index for fast pixel access
        var textureImages = new Dictionary<Texture, Image<Rgba32>>();
        Image<Rgba32>? GetTextureImage(Texture? tex)
        {
            if (tex == null) return null;
            if (textureImages.TryGetValue(tex, out var already)) return already;
            using var s = tex.PrimaryImage.Content.Open();
            var img = Image.Load<Rgba32>(s);
            textureImages[tex] = img;
            return img;
        }

        // Scene traversal with world matrices
        foreach (var scene in model.LogicalScenes)
        {
            foreach (var node in scene.VisualChildren)
                Traverse(node, Matrix4x4.Identity);
        }

        // Dispose images after use
        foreach (var kv in textureImages) kv.Value.Dispose();

        return rows;

        void Traverse(Node n, Matrix4x4 parentWorld)
        {
            var world = parentWorld * n.LocalMatrix;

            if (n.Mesh != null)
            {
                foreach (var prim in n.Mesh.Primitives)
                {
                    // Vertex/Index data (typed)
                    var pos = prim.GetVertexAccessor("POSITION").AsVector3Array();
                    var mat = prim.Material;
                    var ch = mat.FindChannel("BaseColor");
                    int uvSet = ch?.TextureCoordinate ?? 0;  // default to 0 if not specified
                    var uvs = prim.GetVertexAccessor($"TEXCOORD_{uvSet}")?.AsVector2Array();
                    var cols = prim.GetVertexAccessor("COLOR_0")?.AsVector4Array();
                    var indices = prim.GetIndices().ToArray(); // <- fix for Accessor indexing

                    // Material (BaseColor channel)
                    var baseFactor = new float[] { 1, 1, 1, 1 }; // RGBA
                    ch?.Parameter.CopyTo(baseFactor);
                    var baseTex = ch?.Texture; // Texture or null
                    using var img = baseTex != null ? Image.Load<Rgba32>(baseTex.PrimaryImage.Content.Open()) : null;
                    //baseTex.PrimaryImage.Content.SaveToFile("debug_basecolor.png");
                    var bfLin = SrgbToLinear(new Vector3(baseFactor[0], baseFactor[1], baseFactor[2]));

                    // Iterate triangles
                    int triCount = indices.Length / 3;
                    for (int ti = 0; ti < triCount; ti++)
                    {
                        var ia = (int)indices[3 * ti + 0];
                        var ib = (int)indices[3 * ti + 1];
                        var ic = (int)indices[3 * ti + 2];

                        var A = Vector3.Transform(pos[ia], world);
                        var B = Vector3.Transform(pos[ib], world);
                        var C = Vector3.Transform(pos[ic], world);

                        var uva = uvs != null ? uvs[ia] : Vector2.Zero;
                        var uvb = uvs != null ? uvs[ib] : Vector2.Zero;
                        var uvc = uvs != null ? uvs[ic] : Vector2.Zero;

                        var ca = cols != null ? new Vector3(cols[ia].X, cols[ia].Y, cols[ia].Z) : Vector3.One;
                        var cb = cols != null ? new Vector3(cols[ib].X, cols[ib].Y, cols[ib].Z) : Vector3.One;
                        var cc = cols != null ? new Vector3(cols[ic].X, cols[ic].Y, cols[ic].Z) : Vector3.One;

                        var accum = Vector3.Zero;
                        int samples = (img != null && uvs != null) ? 16 : 1;
                        var rng = new Random(ti * 911);

                        for (int s = 0; s < samples; s++)
                        {
                            float u1 = (float)rng.NextDouble();
                            float u2 = (float)rng.NextDouble();
                            float su = 1 - MathF.Sqrt(u1);
                            float sv = MathF.Sqrt(u1) * (1 - u2);
                            float sw = MathF.Sqrt(u1) * u2;

                            var uvS = su * uva + sv * uvb + sw * uvc;
                            var vcS = su * ca + sv * cb + sw * cc;

                            Vector3 texLin = Vector3.One;
                            if (img != null && uvs != null)
                            {
                                float uu = uvS.X - MathF.Floor(uvS.X);
                                float vv = uvS.Y - MathF.Floor(uvS.Y);
                                int x = Math.Clamp((int)(uu * img.Width), 0, img.Width - 1);
                                int y = Math.Clamp((int)(vv * img.Height), 0, img.Height - 1);


                                var p = img[x, y];
                                texLin = SrgbToLinear(new Vector3(p.R / 255f, p.G / 255f, p.B / 255f));
                            }

                            var vcLin = SrgbToLinear(vcS);
                            accum += bfLin * texLin * vcLin;
                        }

                        var avgLin = accum / Math.Max(1, samples);
                        var avgSrgb = LinearToSrgb(avgLin);

                        // ✅ ADD THE ROW
                        rows.Add(new TriangleRow(
                            meshCounter, ti,
                            A.X, A.Y, A.Z,
                            B.X, B.Y, B.Z,
                            C.X, C.Y, C.Z,
                            avgSrgb.X, avgSrgb.Y, avgSrgb.Z
                        ));
                    }
                    // ✅ INCREMENT per primitive (or do it once per mesh)
                    meshCounter++;
                }
            }

            foreach (var c in n.VisualChildren)
                Traverse(c, world);
        }

    }
    static Vector3 SrgbToLinear(Vector3 c) =>
        new Vector3(CompSrgbToLinear(c.X), CompSrgbToLinear(c.Y), CompSrgbToLinear(c.Z));

    static Vector3 LinearToSrgb(Vector3 c) =>
        new Vector3(CompLinearToSrgb(c.X), CompLinearToSrgb(c.Y), CompLinearToSrgb(c.Z));

    static float CompSrgbToLinear(float c) => (c <= 0.04045f) ? c / 12.92f : MathF.Pow((c + 0.055f) / 1.055f, 2.4f);
    static float CompLinearToSrgb(float c) => (c <= 0.0031308f) ? 12.92f * c : 1.055f * MathF.Pow(c, 1f / 2.4f) - 0.055f;

    public static void WriteCsv(string outPath, IEnumerable<TriangleRow> rows)
    {
        using var sw = new StreamWriter(outPath);
        sw.WriteLine("meshIndex,triIndex,ax,ay,az,bx,by,bz,cx,cy,cz,r,g,b");
        foreach (var r in rows)
        {
            sw.WriteLine($"{r.MeshIndex},{r.TriIndex},{r.Ax},{r.Ay},{r.Az},{r.Bx},{r.By},{r.Bz},{r.Cx},{r.Cy},{r.Cz},{r.R},{r.G},{r.B}");
        }
    }
}
