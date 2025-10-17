namespace ImgDebugger
{
    partial class Form1
    {
        /// <summary>
        ///  Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        ///  Clean up any resources being used.
        /// </summary>
        /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form Designer generated code

        /// <summary>
        ///  Required method for Designer support - do not modify
        ///  the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            dbPanel1 = new DBPanel();
            startN = new NumericUpDown();
            startL = new Label();
            countN = new NumericUpDown();
            label1 = new Label();
            ((System.ComponentModel.ISupportInitialize)startN).BeginInit();
            ((System.ComponentModel.ISupportInitialize)countN).BeginInit();
            SuspendLayout();
            // 
            // dbPanel1
            // 
            dbPanel1.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            dbPanel1.Location = new Point(12, 12);
            dbPanel1.Name = "dbPanel1";
            dbPanel1.Size = new Size(505, 345);
            dbPanel1.TabIndex = 0;
            dbPanel1.Paint += dbPanel1_Paint;
            // 
            // startN
            // 
            startN.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            startN.Location = new Point(569, 12);
            startN.Name = "startN";
            startN.Size = new Size(120, 23);
            startN.TabIndex = 1;
            startN.ValueChanged += startN_ValueChanged;
            // 
            // startL
            // 
            startL.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            startL.AutoSize = true;
            startL.Location = new Point(532, 14);
            startL.Name = "startL";
            startL.Size = new Size(31, 15);
            startL.TabIndex = 2;
            startL.Text = "Start";
            // 
            // countN
            // 
            countN.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            countN.Location = new Point(569, 41);
            countN.Name = "countN";
            countN.Size = new Size(120, 23);
            countN.TabIndex = 1;
            countN.ValueChanged += countN_ValueChanged;
            // 
            // label1
            // 
            label1.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            label1.AutoSize = true;
            label1.Location = new Point(523, 43);
            label1.Name = "label1";
            label1.Size = new Size(40, 15);
            label1.TabIndex = 2;
            label1.Text = "Count";
            // 
            // Form1
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            ClientSize = new Size(701, 369);
            Controls.Add(label1);
            Controls.Add(startL);
            Controls.Add(countN);
            Controls.Add(startN);
            Controls.Add(dbPanel1);
            Name = "Form1";
            Text = "Form1";
            Load += Form1_Load;
            ((System.ComponentModel.ISupportInitialize)startN).EndInit();
            ((System.ComponentModel.ISupportInitialize)countN).EndInit();
            ResumeLayout(false);
            PerformLayout();
        }

        #endregion

        private DBPanel dbPanel1;
        private NumericUpDown startN;
        private Label startL;
        private NumericUpDown countN;
        private Label label1;
    }
}
