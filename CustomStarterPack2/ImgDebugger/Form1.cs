namespace ImgDebugger
{
    public partial class Form1 : Form
    {
        public Form1()
        {
            InitializeComponent();
        }

        List<Point> Points = new List<Point>();
        Image img;
        private void Form1_Load(object sender, EventArgs e)
        {
            Points = ReadPts("_points.pts");
            img = Image.FromFile("_debug.png");
            countN.Maximum = Points.Count;
            countN.Value = Points.Count;
        }

        /// <summary>
        /// Reads "points.pts" (fixed name) from either:
        ///  - the directory you pass, or
        ///  - the directory of an image file you pass.
        /// Lines must be "x,y".
        /// </summary>
        public static List<Point> ReadPts(string ptsPath)
        {
            var pts = new List<Point>(4096);
            foreach (var line in File.ReadLines(ptsPath))
            {
                if (string.IsNullOrWhiteSpace(line)) continue;
                var t = line.Split(',');
                if (t.Length != 2) continue;
                if (int.TryParse(t[0].Trim(), out int x) &&
                    int.TryParse(t[1].Trim(), out int y))
                {
                    pts.Add(new Point(x, y));
                }
            }
            return pts;
        }

        private void startN_ValueChanged(object sender, EventArgs e)
        {
            dbPanel1.Invalidate();
            Application.DoEvents();
        }

        private void countN_ValueChanged(object sender, EventArgs e)
        {
            dbPanel1.Invalidate();
            Application.DoEvents();
        }

        private void dbPanel1_Paint(object sender, PaintEventArgs e)
        {
            var g = e.Graphics;
            g.ScaleTransform(0.6f, 0.6f);
            g.Clear(Color.Transparent);
            g.DrawImage(img, 0, 0, img.Width, img.Height);
            // draw points as pixels
            //foreach (var p in Points.Slice((int)startN.Value, (int)countN.Value))
            //    g.FillRectangle(Brushes.Red, p.X - 0.5F, p.Y - 0.5F, 1, 1);

            g.DrawLines(Pens.Red, Points.Slice((int)startN.Value, (int)countN.Value).ToArray());
        }
    }
}
