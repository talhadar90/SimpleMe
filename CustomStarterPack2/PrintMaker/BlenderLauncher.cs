using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

public sealed class BlenderLayoutRunner
{
    public sealed record BlenderLayoutOptions(
        string BlenderExe,             // e.g. @"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
        string ScriptPath,             // e.g. @"F:\CustomStarterPack\starter_pack_card_layout.py"
        string Figure,                 // --figure
        IEnumerable<string>? Acc,      // --acc (0..3)
        double CardWidth,              // --card_width (mm)
        double CardHeight,             // --card_height (mm)
        double CardThickness,          // --card_thickness (mm)
        double UpperRatio = 0.25,      // --upper_ratio
        double MarginAccessories = 2.0,// --margin_accessories
        double MarginFigure = 4.0,     // --margin_figure
        double PaddingCard = 4.0,      // --padding_card
        double Fillet = 5.0,           // --fillet
        bool FlipHead = false,         // --flip_head
        bool AccFrontUp = false,       // --acc_front_up
        string OutDir = "",            // --outdir (required)
        string MidDir = "",            // --middir (required)
        string JobId = "run",          // --job_id
        bool SaveBlend = false,        // --save_blend
        string Title = "Starter Pack", // --title
        string Subtitle = "By M3D",    // --subtitle
        double TS = 14.0,              // --TS
        double MT = 3.0,               // --MT
        double TH = 30.0,              // --TH
        string Font = "",              // --font
        double TextExtr = 0.8,         // --text_extr
        double TextLift = -0.2,         // --text_lift
        bool DontRunBlender = false,    // Don't actually run the blender, only for debugging// add to BlenderLayoutOptions(...)
        bool HasHole = false,             // --has_hole
        double HoleD = 3.0,               // --hole_d (mm)
        double HoleMargin = 4.0,          // --hole_margin (mm)
        string HoleCorner = "top_right",  // --hole_corner: top_right|top_left|bottom_right|bottom_left
        string ModelNameSeed = "card",         // --model_name_seed
        int renderResx = 1000,
        int renderResy = 1000
    )
    {
        public int RenderResx { get; internal set; }
        public int RenderResy { get; internal set; }
    }

    // === PUBLIC API ===
    public static async Task<LayoutPayload> RunAsync(BlenderLayoutOptions opt, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(opt.OutDir))
            throw new ArgumentException("--outdir is required", nameof(opt.OutDir));
        if (string.IsNullOrWhiteSpace(opt.MidDir))
            throw new ArgumentException("--middir is required", nameof(opt.MidDir));

        Directory.CreateDirectory(opt.OutDir);
        Directory.CreateDirectory(opt.MidDir);

        // Build CLI args for Blender -> Python script -> our script args after "--"
        // Blender invocation pattern mirrors your launcher .bat
        var args = new List<string>
        {
            "--background",
            "--python", Quote(opt.ScriptPath),
            "--",
            "--figure", Quote(opt.Figure),
            "--card_width", opt.CardWidth.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--card_height", opt.CardHeight.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--card_thickness", opt.CardThickness.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--upper_ratio", opt.UpperRatio.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--margin_accessories", opt.MarginAccessories.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--margin_figure", opt.MarginFigure.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--padding_card", opt.PaddingCard.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--fillet", opt.Fillet.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--outdir", Quote(opt.OutDir),
            "--middir", Quote(opt.MidDir),
            "--job_id", Quote(opt.JobId),
            "--title", Quote(opt.Title),
            "--subtitle", Quote(opt.Subtitle),
            "--TS", opt.TS.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--MT", opt.MT.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--TH", opt.TH.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--font", Quote(opt.Font),
            "--text_extr", opt.TextExtr.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--text_lift", opt.TextLift.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--model_name_seed", opt.ModelNameSeed.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--render_resx", opt.RenderResx.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--render_resy", opt.RenderResy.ToString(System.Globalization.CultureInfo.InvariantCulture),
        };

        if (opt.Acc is not null)
        {
            var accList = opt.Acc.Where(s => !string.IsNullOrWhiteSpace(s)).Take(3).ToList();
            if (accList.Count > 0)
            {
                args.Add("--acc");
                args.AddRange(accList.Select(Quote));
            }
        }
        if (opt.FlipHead) args.Add("--flip_head");
        if (opt.AccFrontUp) args.Add("--acc_front_up");
        if (opt.SaveBlend) args.Add("--save_blend");

        args.Add("--render_resx"); args.Add(opt.renderResx.ToString(System.Globalization.CultureInfo.InvariantCulture));
        args.Add("--render_resy"); args.Add(opt.renderResy.ToString(System.Globalization.CultureInfo.InvariantCulture));

        if (opt.HasHole) args.Add("--has_hole");
        args.AddRange(new[]
        {
            "--hole_d",        opt.HoleD.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--hole_margin",   opt.HoleMargin.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--hole_corner",   Quote(string.IsNullOrWhiteSpace(opt.HoleCorner) ? "top_right" : opt.HoleCorner)
            });

        // model name seed (optional)
        if (!string.IsNullOrWhiteSpace(opt.ModelNameSeed))
        {
            args.Add("--model_name_seed");
            args.Add(Quote(opt.ModelNameSeed));
        }

        var psi = new ProcessStartInfo
        {
            FileName = opt.BlenderExe,
            Arguments = string.Join(" ", args),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8
        };

        using var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        var stdout = new StringBuilder();
        var stderr = new StringBuilder();
        // Echo lines to the console as they arrive (live).
        proc.OutputDataReceived += (_, e) =>
        {
            if (e.Data is not null) Console.Out.WriteLine(e.Data);
        };
        proc.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is not null) Console.Error.WriteLine(e.Data);
        };
        if (!opt.DontRunBlender)
        {
            if (!proc.Start())
                throw new InvalidOperationException("Failed to start Blender process.");

            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();

            await proc.WaitForExitAsync(ct).ConfigureAwait(false);

            if (proc.ExitCode != 0)
            {
                // Surface useful logs if Blender/script failed
                var msg = $"Blender exited with code {proc.ExitCode}.\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}";
                throw new ApplicationException(msg);
            }
        }

        // Determine the JSON path: script defaults to <outdir>/layout_<job_id>.json unless --layout was passed. :contentReference[oaicite:2]{index=2}
        var jsonPath = Path.Combine(opt.MidDir, opt.ModelNameSeed + "_layout.json");

        if (!File.Exists(jsonPath))
        {
            var msg = $"Expected JSON not found at: {jsonPath}\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}";
            throw new FileNotFoundException(msg, jsonPath);
        }

        // Parse JSON according to the sample structure (meta + items). :contentReference[oaicite:3]{index=3}
        var json = await File.ReadAllTextAsync(jsonPath, ct).ConfigureAwait(false);
        var payload = JsonSerializer.Deserialize<LayoutPayload>(json, JsonOptions)
                      ?? throw new InvalidDataException("JSON deserialized to null.");

        return payload;
    }

    private static string Quote(string s)
        => string.IsNullOrEmpty(s) ? "\"\"" : (s.Contains(' ') || s.Contains('"') ? $"\"{s.Replace("\"", "\\\"")}\"" : s);

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true,
        NumberHandling = JsonNumberHandling.AllowReadingFromString
    };
}

// === JSON models (align with your script’s output schema) ===
// Sample shape: { "meta": { ... }, "items": [ { "name": "...", "center": {x,y}, "size": {w,h}, "rotation_z_deg": 0 } ] } :contentReference[oaicite:4]{index=4}

public sealed class LayoutPayload
{
    [JsonPropertyName("meta")] public Meta Meta { get; set; } = new();
    [JsonPropertyName("items")] public List<Item> Items { get; set; } = new();
}

public sealed class Meta
{
    [JsonPropertyName("job_id")] public string JobId { get; set; } = "";
    [JsonPropertyName("units")] public string Units { get; set; } = "mm";
    [JsonPropertyName("card")] public Card Card { get; set; } = new();
    [JsonPropertyName("slots")] public Slots Slots { get; set; } = new();
}

public sealed class Card
{
    [JsonPropertyName("W")] public double W { get; set; }
    [JsonPropertyName("H")] public double H { get; set; }
    [JsonPropertyName("card_thickness")] public double CardThickness { get; set; }
    [JsonPropertyName("upper_ratio")] public double UpperRatio { get; set; }
    [JsonPropertyName("padding_card")] public double PaddingCard { get; set; }
}

public sealed class Slots
{
    [JsonPropertyName("figure")] public Size Figure { get; set; } = new();
    [JsonPropertyName("accessories")] public Size Accessories { get; set; } = new();
    [JsonPropertyName("text_strip")] public TextStrip TextStrip { get; set; } = new();
}

public sealed class Size { [JsonPropertyName("w")] public double W { get; set; } [JsonPropertyName("h")] public double H { get; set; } }
public sealed class TextStrip { [JsonPropertyName("h")] public double H { get; set; } }

public sealed class Item
{
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("center")] public XY Center { get; set; } = new();
    [JsonPropertyName("size")] public Size Size { get; set; } = new();
    [JsonPropertyName("rotation_z_deg")] public double RotationZDeg { get; set; }
}

public sealed class XY { [JsonPropertyName("x")] public double X { get; set; } [JsonPropertyName("y")] public double Y { get; set; } }
