using netDxf;
using netDxf.Entities;
using netDxf.Header;
using netDxf.Tables;
using netDxf.Units;
using static netDxf.Entities.HatchBoundaryPath;

static class DxfExporterNetDxf
{
    /// Saves all contours as closed LWPOLYLINEs (units = inches).
    /// px→inch via dpi; flips Y (screen→CAD) so it imports upright in AI.
    public static void Save(string path, List<BoundaryDetector.BoundaryInfo> infos, int imageHeightPx, double dpi)
    {
        if (dpi <= 0) dpi = 300.0;
        double pxTomm = 1.0 / dpi * 25.4;

        var dxf = new DxfDocument(DxfVersion.AutoCad2000);
        dxf.DrawingVariables.InsUnits = DrawingUnits.Inches; // physical units for AI import

        // Simple layers (avoid version-specific props)
        var layerObjects = new Layer("OBJECTS") { Color = AciColor.FromTrueColor(0xFFFFFF) };
        var layerHoles = new Layer("HOLES") { Color = AciColor.FromTrueColor(0xFF0000) };
        if (!dxf.Layers.Contains(layerObjects.Name)) dxf.Layers.Add(layerObjects);
        if (!dxf.Layers.Contains(layerHoles.Name)) dxf.Layers.Add(layerHoles);

        foreach (var b in infos)
        {
            var pts = b.BoundaryPixels;
            if (pts == null || pts.Count < 2) continue;

            // De-dup consecutive vertices (AI can choke on zero-length segments)
            var verts = new List<Polyline2DVertex>(pts.Count);
            int lx = int.MinValue, ly = int.MinValue;
            for (int i = 0; i < pts.Count; i++)
            {
                int xpx = pts[i].X, ypx = pts[i].Y;
                if (i == 0 || xpx != lx || ypx != ly)
                {
                    double x = xpx * pxTomm;
                    double y = (imageHeightPx - ypx) * pxTomm; // flip Y for CAD
                    verts.Add(new Polyline2DVertex(x, y));     // bulge=0 (straight)
                    lx = xpx; ly = ypx;
                }
            }
            if (verts.Count < 2) continue;

            var poly = new Polyline2D(verts, true)   // closed LWPOLYLINE
            {
                Layer = b.IsHole ? layerHoles : layerObjects,
            };

            dxf.Entities.Add(poly);  // add entity to the document
        }

        dxf.Save(path);
    }
}
