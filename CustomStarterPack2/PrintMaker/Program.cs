using System;
using System.IO;
using System.Linq;
using System.Numerics;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;
using SixLabors.ImageSharp.Processing;
using SixLabors.ImageSharp.Drawing;
using SixLabors.ImageSharp.Drawing.Processing;
using static BoundaryDetector;
using System.Security.Cryptography.X509Certificates;
using System.Diagnostics;
using SixLabors.ImageSharp.Formats.Png;
using System.Text;
using System.Net.Http.Headers;
using Path = System.IO.Path;
using SixLabors.ImageSharp.Advanced;
using System.Reflection;
using System.Runtime.Intrinsics.Arm;

class Program
{
    static async Task<int> Main(string[] args)
    {
        //try
        {
            // ---- defaults ----
            //string jobID = "aa725d3c-6754-43ef-b296-041106fab2d2";             // REQUIRED (override with --job)
            string jobID = "001";             // REQUIRED (override with --job)
            string workingDir = "";           // --workdir
            string title = "Starter Pack";
            string subtitle = "Everything You Need";
            int dpi = 600;                    // --dpi
            float minStickerSizes_smm = 10f;    // --min_sticker_mm
            float cuttingMargin_mm = 0.0f;         // --cut_margin_mm
            int cutSmoothing_px = 5;


            //// If no args or null -> help
            //if (args == null || args.Length == 0)
            //    return PrintHelp("No arguments provided.");

            // ---- parse CLI (--key value OR --key=value), validate keys ----
            var allowed = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
    { "--job", "--workdir", "--dpi", "--min_sticker_mm", "--cut_margin_mm", "--cut_smoothing" };

            var kv = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < args.Length; i++)
            {
                var s = args[i];
                if (!s.StartsWith("--"))
                    return PrintHelp($"Unexpected token: {s}");

                var eq = s.IndexOf('=');
                string key = eq >= 0 ? s[..eq] : s;
                if (!allowed.Contains(key))
                    return PrintHelp($"Unknown option: {key}");

                string val;
                if (eq >= 0)
                {
                    val = s[(eq + 1)..];
                    if (string.IsNullOrWhiteSpace(val))
                        return PrintHelp($"Missing value for {key}");
                }
                else
                {
                    if (i + 1 >= args.Length || args[i + 1].StartsWith("--"))
                        return PrintHelp($"Missing value for {key}");
                    val = args[++i];
                }
                kv[key] = val;
            }

            // ---- required ----
            if (kv.TryGetValue("--job", out var jobArg) && !string.IsNullOrWhiteSpace(jobArg))
                jobID = jobArg.Trim();
            if (string.IsNullOrWhiteSpace(jobID))
                return PrintHelp("Missing required --job <id>.");

            // ---- optional ----
            if (kv.TryGetValue("--workdir", out var wd)) workingDir = wd.Trim('"');
            if (kv.TryGetValue("--title", out var wdt)) title = wdt.Trim('"');
            if (kv.TryGetValue("--subtitle", out var wdst)) subtitle = wdst.Trim('"');

            if (kv.TryGetValue("--dpi", out var sDpi))
            {
                if (!int.TryParse(sDpi, out var vDpi) || vDpi <= 0)
                    return PrintHelp("Invalid --dpi. Use a positive integer.");
                dpi = vDpi;
            }
            if (kv.TryGetValue("--cut_smoothing", out var sCutSmoothing))
            {
                if (!int.TryParse(sCutSmoothing, out var vCutSmoothing) || vCutSmoothing <= 0)
                    return PrintHelp("Invalid --cut_smoothing. Use a positive integer.");
                cutSmoothing_px = vCutSmoothing;
            }

            if (kv.TryGetValue("--min_sticker_mm", out var sMin))
            {
                if (!float.TryParse(sMin, out var vMin) || vMin <= 0)
                    return PrintHelp("Invalid --min_sticker_mm. Use a positive number.");
                minStickerSizes_smm = vMin;
            }

            if (kv.TryGetValue("--cut_margin_mm", out var sCut))
            {
                if (!float.TryParse(sCut, out var vCut) || vCut < 0)
                    return PrintHelp("Invalid --cut_margin_mm. Use a non-negative number.");
                cuttingMargin_mm = vCut;
            }

            // ---- derived paths ----
            string outDir = Path.Combine(workingDir, Path.Combine("jobs", jobID, "out"));
            string inDir = Path.Combine(workingDir, Path.Combine("jobs", jobID, "in"));
            Directory.CreateDirectory(outDir);
            Directory.CreateDirectory(inDir);

            // log config
            Console.WriteLine($"[CFG] job={jobID}  workdir=\"{workingDir}\"  dpi={dpi}  min_sticker_mm={minStickerSizes_smm}  cut_margin_mm={cuttingMargin_mm}");
            Console.WriteLine($"[CFG] in = {inDir}");
            Console.WriteLine($"[CFG] out= {outDir}");

            //// Render Textures
            //Parallel.ForEach(new string[] { "base_character", "accessory_1", "accessory_2", "accessory_3" }, (file) =>
            //{
            //    var rows = GlbDiffuseAnalyzer.Analyze(Path.Combine(inDir, file + "_3d.glb"), samplesPerTri: 16);
            //    OrthoProjector.RenderOrthographicPNG(rows, new Vector3(0, 0, -1), 3000, 3000, 10, Path.Combine(inDir, file + "_r2d.png"));
            //    var img = Image.Load<Rgba32>(Path.Combine(inDir, file + "_r2d.png"));
            //    img = CropByTransparency(img, 10);
            //    img.SaveAsPng(Path.Combine(inDir, file + "_r2d.png"));
            //});
            // Basic usage

            //// Render Textures
            //foreach(var file in new string[] { "base_character", "accessory_1", "accessory_2", "accessory_3" })
            //{
            //    await BlenderRenderer.RenderOrthographicAsync(new RenderOptions
            //    {
            //        InputGlbPath = Path.Combine(inDir, file + "_3d.glb"),
            //        OutputImagePath = Path.Combine(inDir, file + "_r2d.png"),
            //        Plane = BlenderRenderer.ProjectionPlane.XZ,
            //        ResolutionX = file == "base_character" ? 2000 : 1000,
            //        ResolutionY = file == "base_character" ? 2000 : 1000
            //    });
            //};
            // In your Main method, add this after the existing tasks:
            var tasks = new Task[] {

            CreateAll(
                nameSeed: "keychain",
                inDir: inDir,
                outDir: outDir,
                jobID: jobID,
                dpi: dpi,
                cutSmoothing: cutSmoothing_px,
                cuttingMargin_mm: cuttingMargin_mm * 0.3F,
                minStickerSizes_smm: minStickerSizes_smm * 0.3F,
                width: 130 * 0.3F,
                height: 170 * 0.3F,
                thickness: 2,
                hasHole: true,
                textHeight: 7,
                upperRatio: 0.15F,
                marginFig: 2,
                marginAcc: 1,
                paddingCard: 1.5F,
                cardFillet: 1,
                title: title,
                subtitle: subtitle,
                layoutOnly: false,
                renderResx: (int)(130 * 0.3 / 25.4 * dpi),  // Calculate from keychain width and DPI
                renderResy: (int)(170 * 0.3 / 25.4 * dpi),  // Calculate from keychain height and DPI
                dontCreateBoundaries: true
                ),

            CreateAll(
                nameSeed: "card",
                inDir: inDir,
                outDir: outDir,
                jobID: jobID,
                dpi: dpi,
                cutSmoothing: cutSmoothing_px,
                cuttingMargin_mm: cuttingMargin_mm,
                minStickerSizes_smm: minStickerSizes_smm,
                width: 130,
                height: 170,
                thickness: 5,
                hasHole: false,
                textHeight: 30,
                upperRatio: 0.2F,
                marginFig: 4,
                marginAcc: 2,
                paddingCard: 4,
                cardFillet: 3,
                title: title,
                subtitle: subtitle,
                layoutOnly: false,
                renderResx: (int)(130 / 25.4 * dpi),  // Calculate from card width and DPI
                renderResy: (int)(170 / 25.4 * dpi),  // Calculate from card height and DPI
                dontCreateBoundaries: true),

            };

            Task.WaitAll(tasks);
            await CreateAllSeparateMarkers(
                nameSeed: "card",
                inDir: inDir,
                outDir: outDir,
                dpi: dpi,
                cardWidth: 130,  // Use your actual card width
                cardHeight: 170, // Use your actual card height
                borderSize: 50   // Tune this value based on your render
            );

            await CreateAllSeparateMarkers(
                nameSeed: "keychain",
                inDir: inDir,
                outDir: outDir,
                dpi: dpi,
                cardWidth: 130 * 0.3f,
                cardHeight: 170 * 0.3f,
                borderSize: 15   // Scaled down for keychain
            );
            return 0;
        }

        //catch (Exception ex)
        //{
        //    Console.WriteLine("[ERROR] " + ex.Message);
        //    return 1;
        //}
    }
    static async Task CreateAll(string nameSeed, string inDir, string outDir, string jobID, int dpi, int cutSmoothing, float cuttingMargin_mm, float minStickerSizes_smm, float width, float height, float thickness, bool hasHole, double textHeight, float upperRatio, float marginFig, float marginAcc, float paddingCard, float cardFillet, string title, string subtitle, bool layoutOnly, int renderResx, int renderResy, bool dontCreateBoundaries)
    {
        var result = await BlenderLayoutRunner.RunAsync(
    new BlenderLayoutRunner.BlenderLayoutOptions(
        BlenderExe: @"blender",
        ScriptPath: Path.Combine(AppContext.BaseDirectory, "blender2.py"),
        Figure: Path.Combine(inDir, "base_character_3d.glb"),
        Acc: new[] { Path.Combine(inDir, "accessory_1_3d.glb"), Path.Combine(inDir, "accessory_2_3d.glb"), Path.Combine(inDir, "accessory_3_3d.glb") },
        CardWidth: width,
        CardHeight: height,
        CardThickness: thickness,
        OutDir: outDir,
        MidDir: inDir,
        JobId: jobID,
        DontRunBlender: false,
        ModelNameSeed: nameSeed,
        HasHole: hasHole,
        HoleMargin: 5,
        TH: textHeight,
        UpperRatio:upperRatio,
        MarginFigure: marginFig,
        MarginAccessories: marginAcc,
        PaddingCard: paddingCard,
        Fillet: cardFillet,
        Title: title, 
        Subtitle: subtitle,
        renderResx: renderResx,
        renderResy: renderResy
    )
);
        if (dontCreateBoundaries)
            return;
        Console.WriteLine("Composing priting image");
        // result is your LayoutPayload from Blender
        var composedImage = await ComposeAsync(
            layout: result,
            imagesDir: inDir,
            dpi: dpi,
            layoutOnly: layoutOnly
        );

        Console.Write("Computing cutting path");
        var boundaries = new List<BoundaryInfo>();
        if (!layoutOnly)
            boundaries = BoundaryDetector.DetectBoundaries(composedImage.Clone(), alphaThreshold: 1).FindAll(info => info.BBox.Width * info.BBox.Height / (float)dpi / dpi * 25.4 * 25.4 > minStickerSizes_smm);

        // run greedy contour ordering on all paths
        for (int i = 0; i < boundaries.Count; i++)
        {
            BoundaryDetector.OrderContourGreedy(boundaries[i]);
            //BoundaryDetector.SmoothBoundary(infos[i], iterations: 3, window: 3, assumeClosed: true);
            BoundaryDetector.TrimAfterClosureByDistance(boundaries[i], 5);
            BoundaryDetector.SmoothBoundary(boundaries[i], iterations: cutSmoothing, window: 20, assumeClosed: true);
            BoundaryDetector.TrimAfterClosureByDistance(boundaries[i], 60);
            //BoundaryDetector.PaintBoundaryAA(composedImage, infos[i], new Rgba32(255, 0, 0, 255), thickness: 2f);
            Console.Write(".");
        }
        //var dInd = boundaries.FindIndex(b => b.AreaPixels == boundaries.Max(b2 => b2.AreaPixels));
        //debugPath(composedImage, boundaries.Find(b => b.AreaPixels == boundaries.Max(b2 => b2.AreaPixels)).BoundaryPixels, "F:\\CustomStarterPack\\CustomStarterPack\\ImgDebugger\\bin\\Debug\\net8.0-windows");
        // Append the image-sized rounded rectangle (e.g., 3 mm radius)
        float mm = cardFillet;
        float radiusPx = (float)(mm * dpi / 25.4);
        var frame = BoundaryDetector.MakeRoundedRectBoundary(
            id: boundaries.Count + 1,
            width: composedImage.Width,
            height: composedImage.Height,
            radiusPx: radiusPx,
            cornerSegments: 20,
            layoutOnly: layoutOnly
        );
        boundaries.Add(frame);
        Console.WriteLine(boundaries.Count + " cuts prepared");

        Image<Rgba32> finalImage = composedImage;
        if (cuttingMargin_mm > 0 && !layoutOnly)
        {
            Console.WriteLine("Generating content for cutting margin");
            // Lets create bleed by picking up some inwards pixels.
            int rErrodPx = Math.Max(1, (int)Math.Round(cuttingMargin_mm / 2 * dpi / 25.4));
            int rPx = Math.Max(1, (int)Math.Round(cuttingMargin_mm * dpi / 25.4));
            var errodedComposedImage = ErodeByAlpha(composedImage, rErrodPx, 128);
            using var bleed = MakeContentAwareBleed(
                src: errodedComposedImage,
                rPx: rPx,
                alphaThreshold: 1,
                featherPx: 0       // soften last few pixels; set 0 for hard edge
            );

            // Lets featherout the edges because we can now see the bleed beneath it,
            var featheredComposedImage = FeatherInwardByAlpha(composedImage, dpi / 300);

            // Put bleed underneath the composed artwork
            finalImage = new Image<Rgba32>(composedImage.Width, composedImage.Height);
            finalImage.Mutate(ctx => ctx
                .DrawImage(bleed, new Point(0, 0), 1f)
                .DrawImage(featheredComposedImage, new Point(0, 0), 1f)
            );
        }
        Console.WriteLine("Saving data");
        
        var refImage = finalImage.Clone();
        if (layoutOnly)
        {
            for (int i = 0; i < boundaries.Count; i++)
                BoundaryDetector.PaintBoundaryAA(refImage, boundaries[i], new Rgba32(255, 0, 0, 255), thickness: 2f);

            SavePngWithDpi(refImage, Path.Combine(outDir, nameSeed + "_placement.png"), dpi);
            Console.WriteLine("Saved printing file at: " + Path.Combine(outDir, nameSeed + "_placement.png"));
        }
        else
        {
            SavePngWithDpi(finalImage, Path.Combine(outDir, nameSeed + "_printing.png"), dpi);
            Console.WriteLine("Saved printing file at: " + Path.Combine(outDir, nameSeed + "_printing.png"));

            for (int i = 0; i < boundaries.Count; i++)
                BoundaryDetector.PaintBoundaryAA(refImage, boundaries[i], new Rgba32(255, 0, 0, 255), thickness: 2f);

            SavePngWithDpi(refImage, Path.Combine(outDir, nameSeed + "_reference.png"), dpi);
            Console.WriteLine("Saved reference image at: " + Path.Combine(outDir, nameSeed + "_reference.png"));

            // Save vectors as DXF (units = inches; pixel→inch via DPI)
            DxfExporterNetDxf.Save(Path.Combine(outDir, nameSeed + "_cutting.dxf"), boundaries, composedImage.Height, dpi);

            Console.WriteLine("Saved cutting DXF at: " + Path.Combine(outDir, nameSeed + "_cutting.dxf"));
        }

        Console.WriteLine("All Done. Exiting...");
        // OR to distinguish holes:
        // BoundaryDetector.PaintBoundaries(canvas, infos, new Rgba32(255,0,0,255), new Rgba32(0,255,0,255), thickness: 2);
    }
    static async Task CreateAllSeparateMarkers(string nameSeed, string inDir, string outDir, int dpi,
    float cardWidth, float cardHeight, int borderSize = 50)
    {
        Console.WriteLine($"Processing separate markers for: {nameSeed}");

        // Paths for the Blender render
        string renderPath = Path.Combine(inDir, nameSeed + $"_scene_render.png");

        if (!File.Exists(renderPath))
        {
            Console.WriteLine($"Warning: Scene render not found at {renderPath}");
            return;
        }

        // Load the Blender render
        using var renderedImageOrg = await Image.LoadAsync<Rgba32>(renderPath);
        using var renderedImage = CropByTransparency(renderedImageOrg, 10);
        // Convert card dimensions from mm to pixels
        double mmToPx = dpi / 25.4;
        int targetWidthPx = (int)Math.Round(cardWidth * mmToPx);
        int targetHeightPx = (int)Math.Round(cardHeight * mmToPx);

        Console.WriteLine($"Target dimensions: {targetWidthPx}x{targetHeightPx} pixels");

        // Resize the render to target dimensions first
        renderedImage.Mutate(ctx => ctx.Resize(new ResizeOptions
        {
            Size = new SixLabors.ImageSharp.Size(targetWidthPx, targetHeightPx),
            Mode = ResizeMode.Stretch,
            Sampler = KnownResamplers.Bicubic
        }));

        // 1. Create main image (without border markers)
        var mainImage = RemoveBorder(renderedImage, borderSize);

        // Save main image (without border markers)
        string mainOutputPath = Path.Combine(outDir, $"{nameSeed}_main.png");
        SavePngWithDpi(mainImage, mainOutputPath, dpi);
        Console.WriteLine($"Saved main image (no border markers): {mainOutputPath}");

        // 2. Create markers only image (only border markers)
        var markersImage = KeepOnlyBorder(renderedImage, borderSize);

        // Save markers only image
        string markersOutputPath = Path.Combine(outDir, $"{nameSeed}_markers.png");
        SavePngWithDpi(markersImage, markersOutputPath, dpi);
        Console.WriteLine($"Saved markers only: {markersOutputPath}");

        // 3. Save the original combined render
        string originalOutputPath = Path.Combine(outDir, $"{nameSeed}_reference.png");
        SavePngWithDpi(renderedImage, originalOutputPath, dpi);
        Console.WriteLine($"Saved original combined: {originalOutputPath}");
    }

    static Image<Rgba32> RemoveBorder(Image<Rgba32> src, int borderSize)
    {
        // Create a copy
        var result = src.Clone();

        // Make border region transparent
        for (int y = 0; y < result.Height; y++)
        {
            var row = result.DangerousGetPixelRowMemory(y).Span;

            for (int x = 0; x < result.Width; x++)
            {
                // Check if pixel is in border region
                if (x < borderSize || x >= result.Width - borderSize ||
                    y < borderSize || y >= result.Height - borderSize)
                {
                    row[x] = new Rgba32(0, 0, 0, 0); // Make transparent
                }
            }
        }

        return result;
    }

    static Image<Rgba32> KeepOnlyBorder(Image<Rgba32> src, int borderSize)
    {
        // Create a copy
        var result = src.Clone();

        // Make center region transparent (keep only border)
        for (int y = 0; y < result.Height; y++)
        {
            var row = result.DangerousGetPixelRowMemory(y).Span;

            for (int x = 0; x < result.Width; x++)
            {
                // Check if pixel is NOT in border region (i.e., in center)
                if (x >= borderSize && x < result.Width - borderSize &&
                    y >= borderSize && y < result.Height - borderSize)
                {
                    row[x] = new Rgba32(0, 0, 0, 0); // Make transparent
                }
            }
        }

        return result;
    }

    // ---- help printer ----
    static int PrintHelp(string? error = null)
    {
        if (!string.IsNullOrWhiteSpace(error))
            Console.Error.WriteLine($"Error: {error}\n");

        Console.WriteLine(
@"Usage:
  PrintMaker --job <id> [--workdir <path>] [--dpi <int>] [--min_sticker_mm <float>] [--cut_margin_mm <float>]

Required:
  --job <id>                Job identifier (e.g., 001)

Optional:
  --workdir <path>          Base working directory (default: current dir)
  --dpi <int>               Output DPI (default: 300)
  --min_sticker_mm <float>  Minimum sticker size in square mm (default: 10)
  --cut_margin_mm <float>   Extra cut margin (bleed) in mm (default: 1)
  --cut_smoothing <float>   Smoothen the cut (default: 10 (iterations))

Examples:
  PrintMaker --job 001
  PrintMaker --job 042 --workdir ""C:\Projects\StarterPack"" --dpi 300 --min_sticker_mm 12.5 --cut_margin_mm 2
  PrintMaker --job=007 --dpi=600
Assumptions: under jobs/<id>/in (relative to --workdir) we read a main model figure.glb, up to four accessories accessory_1_3d.glb…accessory_3_3d.glb, their rembg counterparts figure.png and accessory_1_r2d.png…accessory_3_r2d.png, plus any extra art; under jobs/<id>/out we read if present layout_<id>.json (from Blender) and we write Blender artifacts (model.blend, optional *_text*.png), and the final outputs print<id>.png and print<id>.dxf; the app therefore requires read access to jobs/<id>/in and write access to both jobs/<id>/in and jobs/<id>/out (e.g., to save intermediate or normalized files).
");
        return 2; // non-zero for usage/error
    }
    /// <summary>
    /// Compose a 300 DPI canvas and place items using LayoutPayload geometry.
    /// </summary>
    /// <param name="layout">Blender JSON result.</param>
    /// <param name="imagesDir">Folder containing base_character_r2d.png, accessory_1_r2d.png, …</param>
    /// <param name="outPath">Output PNG file.</param>
    /// <param name="dpi">Target DPI (default 300).</param>
    /// <param name="yUpCoordinates">If true, flip Y (Blender Y-up -> image Y-down).</param>
    /// <param name="invertRotationSign">If true, rotate by -rotation_z_deg (Blender CCW -> image CW).</param>
    public static async Task<Image<Rgba32>> ComposeAsync(
        LayoutPayload layout,
        string imagesDir,
        int dpi = 300,
        bool layoutOnly = false)
    {
        if (layout is null) throw new ArgumentNullException(nameof(layout));
        if (string.IsNullOrWhiteSpace(imagesDir) && !layoutOnly) throw new ArgumentException("imagesDir required");

        double mmToPx = dpi / 25.4; // same as before
        int canvasW = (int)Math.Round(layout.Meta.Card.W * mmToPx);
        int canvasH = (int)Math.Round(layout.Meta.Card.H * mmToPx);

        using var canvas = new Image<Rgba32>(canvasW, canvasH);
        canvas.Metadata.HorizontalResolution = dpi;
        canvas.Metadata.VerticalResolution = dpi;
        if (layoutOnly)
            return canvas.Clone();

        // ---- Global coordinate transform (mm → px) ----
        // Blender center-origin (0,0) with Y-up  -->  image top-left (0,0) with Y-down
        double halfWmm = layout.Meta.Card.W * 0.5;
        double halfHmm = layout.Meta.Card.H * 0.5;

        Func<double, double> XmmToPx = x_mm => (x_mm + halfWmm) * mmToPx; // shift right by W/2, then scale
        Func<double, double> YmmToPx = y_mm => (halfHmm - y_mm) * mmToPx; // flip Y and shift down by H/2
                                                                          // === 0.2 mm black border around the card ===
        //double strokeMm = 0.2;
        //float strokePx = (float)(strokeMm * mmToPx);

        //// Because strokes are centered on the path, inset by half the stroke so the entire line stays inside the canvas
        //var borderRect = new RectangleF(
        //    strokePx / 2f,
        //    strokePx / 2f,
        //    canvasW - strokePx,
        //    canvasH - strokePx
        //);

        //canvas.Mutate(c =>
        //{
        //    // Transparent background by default; just draw the border
        //    c.Draw(Color.Black, strokePx, borderRect);
        //});


        foreach (var it in layout.Items)
        {
            var srcPath = ResolveImagePath(imagesDir, it.Name);
            if (!File.Exists(srcPath))
                continue;

            // target size in px (sizes are lengths, so only scale; no translation/flip)
            int targetW = Math.Max(1, (int)Math.Round(it.Size.W * mmToPx));
            int targetH = Math.Max(1, (int)Math.Round(it.Size.H * mmToPx));

            // center in px using global transform
            double cx = XmmToPx(it.Center.X);
            double cy = YmmToPx(it.Center.Y);

            // rotation (Blender CCW vs image CW)
            float angle = (float)(-it.RotationZDeg);

            using var src = CropByTransparency(await Image.LoadAsync<Rgba32>(srcPath), 10);

            src.Mutate(m => m.Resize(new ResizeOptions
            {
                Size = new SixLabors.ImageSharp.Size(targetW, targetH),
                Mode = ResizeMode.Stretch,
                Sampler = KnownResamplers.Bicubic
            }));

            using var rotated = src.Clone(m => m.Rotate(angle));

            // place so that center aligns to (cx, cy)
            int x = (int)Math.Round(cx - rotated.Width / 2.0);
            int y = (int)Math.Round(cy - rotated.Height / 2.0);

            // Debug visuals: red rect = placed bounds, blue crosshair = intended center
            var rect = new Rectangle(x, y, rotated.Width, rotated.Height);
            canvas.Mutate(m =>
            {
                //m.Draw(Color.Red, 2, rect);
                //m.DrawLine(Color.Blue, 1, new PointF((float)cx - 10, (float)cy), new PointF((float)cx + 10, (float)cy));
                //m.DrawLine(Color.Blue, 1, new PointF((float)cx, (float)cy - 10), new PointF((float)cx, (float)cy + 10));
                m.DrawImage(rotated, new Point(x, y), 1f);
            });
        }


        // Save PNG with good defaults
        var encoder = new PngEncoder
        {
            CompressionLevel = PngCompressionLevel.BestCompression,
            ColorType = PngColorType.RgbWithAlpha,
            TransparentColorMode = PngTransparentColorMode.Preserve
        };
        var toReturn = canvas.Clone();
        return toReturn;
    }
    public static Image<Rgba32> CropByTransparency(Image<Rgba32> src, byte alphaThreshold)
    {
        int w = src.Width, h = src.Height;
        int minX = w, minY = h, maxX = -1, maxY = -1;

        src.ProcessPixelRows(accessor =>
        {
            for (int y = 0; y < h; y++)
            {
                var row = accessor.GetRowSpan(y);
                for (int x = 0; x < w; x++)
                {
                    if (row[x].A >= alphaThreshold)
                    {
                        if (x < minX) minX = x;
                        if (y < minY) minY = y;
                        if (x > maxX) maxX = x;
                        if (y > maxY) maxY = y;
                    }
                }
            }
        });

        Image<Rgba32> result;
        if (maxX < minX || maxY < minY)
        {
            // fully transparent → return 1x1 transparent
            result = new Image<Rgba32>(1, 1);
        }
        else
        {
            var rect = new Rectangle(minX, minY, maxX - minX + 1, maxY - minY + 1);
            result = src.Clone(ctx => ctx.Crop(rect));
        }

        // preserve DPI / resolution metadata
        result.Metadata.HorizontalResolution = src.Metadata.HorizontalResolution;
        result.Metadata.VerticalResolution = src.Metadata.VerticalResolution;
        result.Metadata.ResolutionUnits = src.Metadata.ResolutionUnits;

        return result;
    }

    /// <summary>
    /// Map item names to image files.
    /// Adjust to your exact naming if needed.
    /// </summary>
    private static string ResolveImagePath(string imagesDir, string itemName)
    {
        // Examples:
        // name: "figure" -> images\base_character_r2d.png
        // name: "accessory_1" -> images\accessory_1_r2d.png
        // name: "accessory_2" -> images\accessory_2_r2d.png
        // If the Blender names differ (e.g., "acc1"), tweak the parsing here.

        var name = itemName.Trim().ToLowerInvariant();

        if (name.Contains("figure"))
            return Path.Combine(imagesDir, "base_character_r2d.png");

        if (name.StartsWith("accessory_"))
        {
            // pull the trailing index
            var idxPart = name.Substring("accessory_".Length);
            return Path.Combine(imagesDir, $"accessory_{idxPart}_r2d.png");
        }
        if (name == "textgroup")
        {
            return Path.Combine(imagesDir, $"TextGroup.png");
        }

        // Fallback: try "<name>_r2d.png"
        return Path.Combine(imagesDir, $"{name}_r2d.png");
    }

    /// <summary>
    /// Inward feather on alpha: for every opaque pixel, compute distance (in pixels)
    /// to the nearest transparent pixel; if distance &lt;= radiusPx, scale alpha
    /// linearly: newA = oldA * (dist / radiusPx). RGB channels are unchanged.
    /// </summary>
    /// <param name="src">Input RGBA image.</param>
    /// <param name="radiusPx">Feather radius in pixels (>=1).</param>
    /// <param name="alphaThreshold">Alpha threshold used to define "opaque".</param>
    /// <returns>New image with inward-feathered alpha.</returns>
    public static Image<Rgba32> FeatherInwardByAlpha(Image<Rgba32> src, int radiusPx, byte alphaThreshold = 1)
    {
        if (radiusPx <= 0) return src.Clone();

        int W = src.Width, H = src.Height;

        // Build opaque mask and distance map (seed from transparent pixels)
        var dist = new int[W, H];
        const int INF = int.MaxValue / 4;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++)
                dist[x, y] = INF;

        var q = new Queue<(int x, int y)>(W * H / 8);

        // Seeds: all pixels that are *transparent* (alpha < threshold)
        for (int y = 0; y < H; y++)
        {
            var row = src.DangerousGetPixelRowMemory(y).Span;
            for (int x = 0; x < W; x++)
            {
                if (row[x].A < alphaThreshold)
                {
                    dist[x, y] = 0;
                    q.Enqueue((x, y));
                }
            }
        }

        if (q.Count == 0)
        {
            // Entire image opaque; nothing to feather.
            return src.Clone();
        }

        // 8-connected BFS out to radius
        ReadOnlySpan<(int dx, int dy)> N8 = stackalloc (int, int)[]
        { (-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1) };

        while (q.Count > 0)
        {
            var (x, y) = q.Dequeue();
            int d = dist[x, y];
            if (d >= radiusPx) continue;

            foreach (var (dx, dy) in N8)
            {
                int nx = x + dx, ny = y + dy;
                if ((uint)nx >= (uint)W || (uint)ny >= (uint)H) continue;
                int nd = d + 1;
                if (nd < dist[nx, ny])
                {
                    dist[nx, ny] = nd;
                    q.Enqueue((nx, ny));
                }
            }
        }

        // Apply inward feather: scale alpha for opaque pixels near the edge
        var dst = src.Clone();
        for (int y = 0; y < H; y++)
        {
            var inRow = src.DangerousGetPixelRowMemory(y).Span;
            var outRow = dst.DangerousGetPixelRowMemory(y).Span;

            for (int x = 0; x < W; x++)
            {
                var p = inRow[x];
                if (p.A >= alphaThreshold)
                {
                    int d = dist[x, y];
                    if (d <= radiusPx)
                    {
                        // d == 0 → exactly on/next to the transparent edge → alpha 0
                        // d == radius → keep original alpha
                        float t = d / (float)Math.Max(1, radiusPx); // 0..1
                        byte newA = (byte)Math.Clamp((int)Math.Round(p.A * t), 0, 255);
                        p.A = newA;
                    }
                }
                outRow[x] = p;
            }
        }

        return dst;
    }
    /// <summary>
    /// Erode by alpha: removes the outer opaque ring by radiusPx (disk).
    /// Pixels that fail the erosion test have their alpha set to 0; RGB is left unchanged.
    /// </summary>
    /// <param name="src">Input RGBA image.</param>
    /// <param name="radiusPx">Disk radius in pixels (>=1). Use a few px (e.g., 1–4).</param>
    /// <param name="alphaThreshold">Alpha considered opaque (default 1).</param>
    /// <returns>New image with eroded alpha.</returns>
    public static Image<Rgba32> ErodeByAlpha(Image<Rgba32> src, int radiusPx, byte alphaThreshold = 1)
    {
        if (radiusPx <= 0) return src.Clone();

        int W = src.Width, H = src.Height;

        // Build opaque mask (alpha >= threshold)
        var solid = new bool[W, H];
        for (int y = 0; y < H; y++)
        {
            var row = src.DangerousGetPixelRowMemory(y).Span;
            for (int x = 0; x < W; x++)
                solid[x, y] = row[x].A >= alphaThreshold;
        }

        // Precompute disk offsets
        var offsets = new List<(int dx, int dy)>(4 * radiusPx * radiusPx + 4);
        int r2 = radiusPx * radiusPx;
        for (int dy = -radiusPx; dy <= radiusPx; dy++)
            for (int dx = -radiusPx; dx <= radiusPx; dx++)
                if (dx * dx + dy * dy <= r2)
                    offsets.Add((dx, dy));

        // Erode: pixel stays opaque only if ALL neighbors within the disk are opaque
        var keep = new bool[W, H];
        for (int y = 0; y < H; y++)
        {
            for (int x = 0; x < W; x++)
            {
                bool ok = true;
                foreach (var (dx, dy) in offsets)
                {
                    int sx = x + dx, sy = y + dy;
                    if (!((uint)sx < (uint)W && (uint)sy < (uint)H) || !solid[sx, sy])
                    { ok = false; break; }
                }
                keep[x, y] = ok;
            }
        }

        // Apply: zero alpha where erosion failed; leave RGB as-is
        var outImg = src.Clone();
        for (int y = 0; y < H; y++)
        {
            var row = outImg.DangerousGetPixelRowMemory(y).Span;
            for (int x = 0; x < W; x++)
            {
                if (!keep[x, y])
                {
                    var p = row[x];
                    p.A = 0;
                    row[x] = p;
                }
            }
        }

        return outImg;
    }

    /// <summary>
    /// Content-aware bleed: grows opaque regions by rPx using multi-source BFS (Voronoi),
    /// filling previously transparent pixels with the nearest island's color.
    /// Returns a bleed layer (RGBA) you can composite under your canvas.
    /// </summary>
    public static Image<Rgba32> MakeContentAwareBleed(Image<Rgba32> src, int rPx, byte alphaThreshold = 1, int featherPx = 2)
    {
        int W = src.Width, H = src.Height;
        var dist = new int[W, H];
        var seed = new Rgba32[W, H];
        var q = new Queue<(int x, int y)>(W * H / 8);

        const int INF = int.MaxValue / 4;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++)
                dist[x, y] = INF;

        // Seed from opaque pixels
        for (int y = 0; y < H; y++)
        {
            var row = src.DangerousGetPixelRowMemory(y).Span;
            for (int x = 0; x < W; x++)
            {
                var p = row[x];
                if (p.A >= alphaThreshold)
                {
                    dist[x, y] = 0;
                    seed[x, y] = p;
                    q.Enqueue((x, y));
                }
            }
        }

        if (q.Count == 0 || rPx <= 0)
            return new Image<Rgba32>(W, H); // nothing to grow

        // 8-connected BFS up to rPx
        ReadOnlySpan<(int dx, int dy)> N8 = stackalloc (int, int)[]
        { (-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1) };

        while (q.Count > 0)
        {
            var (x, y) = q.Dequeue();
            int d = dist[x, y];
            if (d >= rPx) continue;

            foreach (var (dx, dy) in N8)
            {
                int nx = x + dx, ny = y + dy;
                if ((uint)nx >= (uint)W || (uint)ny >= (uint)H) continue;
                int nd = d + 1;
                if (nd < dist[nx, ny])
                {
                    dist[nx, ny] = nd;
                    seed[nx, ny] = seed[x, y];
                    q.Enqueue((nx, ny));
                }
            }
        }

        // Build bleed layer using nearest colors; feather last 'featherPx' pixels
        var bleed = new Image<Rgba32>(W, H);
        for (int y = 0; y < H; y++)
        {
            var srcRow = src.DangerousGetPixelRowMemory(y).Span;
            var outRow = bleed.DangerousGetPixelRowMemory(y).Span;

            for (int x = 0; x < W; x++)
            {
                if (srcRow[x].A >= alphaThreshold) continue; // original already opaque

                int d = dist[x, y];
                if (d <= rPx)
                {
                    var c = seed[x, y];
                    byte a = 255;
                    if (featherPx > 0)
                    {
                        int edge = System.Math.Max(0, rPx - featherPx);
                        if (d > edge)
                        {
                            float t = (float)(rPx - d) / System.Math.Max(1, featherPx); // 0..1
                            a = (byte)System.Math.Clamp((int)(255 * t), 0, 255);
                        }
                    }
                    outRow[x] = new Rgba32(c.R, c.G, c.B, a);
                }
            }
        }

        return bleed;
    }
    static void SavePngWithDpi(Image<Rgba32> img, string path, int dpi)
    {
        if (dpi <= 0) dpi = 300;

        // Set metadata DPI (PixelsPerInch); ImageSharp will encode PNG pHYs accordingly.
        img.Metadata.VerticalResolution = dpi;
        img.Metadata.HorizontalResolution = dpi;
        img.Metadata.ResolutionUnits = SixLabors.ImageSharp.Metadata.PixelResolutionUnit.PixelsPerInch;

        var enc = new PngEncoder
        {
            ColorType = PngColorType.RgbWithAlpha,
            CompressionLevel = PngCompressionLevel.Level6,
            FilterMethod = PngFilterMethod.Adaptive,
            InterlaceMethod = PngInterlaceMode.None,
            TransparentColorMode = PngTransparentColorMode.Preserve,
            SkipMetadata = false
        };

        Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path)!);
        img.Save(path, enc);
    }
    static void debugPath(Image img, List<Point> points, string path)
    {
        File.WriteAllLines("_points.pts", points.Select(p => $"{p.X},{p.Y}"));
        img.SaveAsPng("_debug.png");
        Process.Start(Path.Combine(path, "ImgDebugger.exe"));
    }

    class Options
    {
        public double HeightInches = 6; // if >0, overrides H in pixels
        public int Dpi = 300;             // PNG DPI (and pixel/in mapping for DXF)

        public string MainPath = "";
        public string[] Accessories = Array.Empty<string>();
        public string OutputPath = "";
        public int H = 1600;
        public int Margin = 24;
        public int Gap = 32;
        public int Padding = 48;

        // Default demo folder + files (when args are null/empty)
        private static readonly string DefaultDir = @"F:\CustomStarterPack\trans";
        private static readonly string DefaultMain = System.IO.Path.Combine(DefaultDir, "main.png");
        private static readonly string[] DefaultAcc =
        {
            System.IO.Path.Combine(DefaultDir, "acc0.png"),
            System.IO.Path.Combine(DefaultDir, "acc1.png"),
            System.IO.Path.Combine(DefaultDir, "acc2.png"),
            System.IO.Path.Combine(DefaultDir, "acc3.png"),
        };
        private static readonly string DefaultOut = System.IO.Path.Combine(DefaultDir, "toyset_layout.png");

        public static Options? Parse(string[]? args)
        {
            // If args are null or empty → use defaults
            if (args == null || args.Length == 0)
            {
                Console.WriteLine("[INFO] No arguments provided. Using default demo files from:");
                Console.WriteLine($"       {DefaultDir}");
                var o = new Options
                {
                    MainPath = DefaultMain,
                    Accessories = DefaultAcc,
                    OutputPath = DefaultOut,
                    H = 1600,
                    Margin = 24,
                    Gap = 32,
                    Padding = 48,
                };
                ValidateFiles(o.MainPath, o.Accessories);
                return o;
            }

            var opt = new Options();

            for (int i = 0; i < args.Length; i++)
            {
                switch (args[i])
                {
                    case "--main":
                        opt.MainPath = args[++i]; break;
                    case "--acc":
                        var list = new System.Collections.Generic.List<string>();
                        int j = i + 1;
                        while (j < args.Length && !args[j].StartsWith("--"))
                        {
                            list.Add(args[j]);
                            j++;
                        }
                        opt.Accessories = list.ToArray();
                        i = j - 1;
                        break;
                    case "--out":
                        opt.OutputPath = args[++i]; break;
                    case "--H":
                        opt.H = int.Parse(args[++i]); break;
                    case "--margin":
                        opt.Margin = int.Parse(args[++i]); break;
                    case "--gap":
                        opt.Gap = int.Parse(args[++i]); break;
                    case "--padding":
                        opt.Padding = int.Parse(args[++i]); break;
                    case "--height_in":
                        opt.HeightInches = double.Parse(args[++i]); break;
                    case "--dpi":
                        opt.Dpi = int.Parse(args[++i]); break;
                    default:
                        throw new ArgumentException($"Unknown arg: {args[i]}");
                }
            }

            if (string.IsNullOrWhiteSpace(opt.MainPath) ||
                string.IsNullOrWhiteSpace(opt.OutputPath) ||
                opt.Accessories.Length == 0)
            {
                throw new ArgumentException("Missing --main, --acc (x4), or --out.");
            }

            ValidateFiles(opt.MainPath, opt.Accessories);
            return opt;
        }

        private static void ValidateFiles(string mainPath, string[] accessories)
        {
            if (!File.Exists(mainPath))
                throw new FileNotFoundException($"Main image not found: {mainPath}");
            foreach (var p in accessories)
                if (!File.Exists(p))
                    throw new FileNotFoundException($"Accessory image not found: {p}");
        }
    }

    sealed class DisposeAll : IDisposable
    {
        private readonly IDisposable[] _items;
        public DisposeAll(params IDisposable[] items) => _items = items;
        public void Dispose() { foreach (var i in _items) i.Dispose(); }
    }

}
