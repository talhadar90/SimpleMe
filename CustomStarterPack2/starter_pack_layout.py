# starter_pack_layout.py
# One-file Blender layout script for "starter pack" placement.
# Works in Blender 3.x/4.x (tested 4.5). No external deps.

import bpy, os, sys, math, json, argparse, mathutils
from math import radians
from mathutils import Vector, Matrix

# ----------------------------- CLI -----------------------------
def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    # Inputs
    p.add_argument("--figure", required=True)
    p.add_argument("--accessories", nargs="*", default=[])
    p.add_argument("--outdir", required=True)
    p.add_argument("--job_id", default="run")

    # Layout (mm)
    p.add_argument("--base_w", type=float, default=130.0)
    p.add_argument("--base_h", type=float, default=190.0)
    p.add_argument("--base_th", type=float, default=5.0)
    p.add_argument("--text_h", type=float, default=50.0)
    p.add_argument("--figure_w", type=float, default=70.0)
    p.add_argument("--figure_h", type=float, default=140.0)
    p.add_argument("--gap", type=float, default=10.0)
    p.add_argument("--acc_size", type=float, default=30.0)
    p.add_argument("--acc_count", type=int, default=4)

    # Behavior
    p.add_argument("--export_stl", action="store_true")
    p.add_argument("--title", default="Starter Pack")
    p.add_argument("--subtitle", default="Designed by M3D")
    p.add_argument("--font", default="")  # path to .ttf (optional)
    return p.parse_args(argv)

# ----------------------------- utils -----------------------------
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def set_units_mm():
    s = bpy.context.scene
    s.unit_settings.system = 'METRIC'
    # 1 Blender unit = 1 m; scale_length scales displayed units.
    # We want numbers in mm, so set 1 BU -> 1000 mm => scale_length=0.001
    s.unit_settings.scale_length = 0.001

def ensure_outdir(path):
    os.makedirs(path, exist_ok=True)

def select_only(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def apply_all_transforms(obj):
    select_only(obj)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

def pick_largest_mesh(objs):
    meshes = [o for o in objs if o.type == 'MESH']
    if not meshes:
        return None
    # choose by vertex count, fallback to bound_box volume
    meshes.sort(key=lambda o: (len(o.data.vertices), o.dimensions.x * o.dimensions.y * o.dimensions.z), reverse=True)
    return meshes[0]

def import_model(path, name_hint="Model"):
    before = set(bpy.context.scene.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
    after = set(bpy.context.scene.objects)
    new = list(after - before)
    root = pick_largest_mesh(new) or (new[0] if new else None)
    if root:
        root.name = name_hint
    return root, new

def world_aabb(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(deps)
    mat = eval_obj.matrix_world
    # bound_box is local 8 points
    pts = [mat @ Vector(c) for c in eval_obj.bound_box]
    xs = [p.x for p in pts]; ys = [p.y for p in pts]; zs = [p.z for p in pts]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

def world_dims(obj):
    mn, mx = world_aabb(obj)
    return Vector((mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2]))

def center_xy_on_origin(obj):
    mn, mx = world_aabb(obj)
    cx = 0.5*(mn[0]+mx[0]); cy = 0.5*(mn[1]+mx[1])
    obj.location.x -= cx
    obj.location.y -= cy

def rest_on_z0(obj):
    mn, mx = world_aabb(obj)
    obj.location.z -= mn[2]

def try_orient_longest_X_second_Y(obj):
    """
    Find a rotation that makes bbox dims sorted X>=Y>=Z (lay-flat, long axis horizontal).
    Test a small set of candidate rotations (right-handed).
    """
    candidates = []
    def Rx(a): return Matrix.Rotation(radians(a), 4, 'X')
    def Ry(a): return Matrix.Rotation(radians(a), 4, 'Y')
    def Rz(a): return Matrix.Rotation(radians(a), 4, 'Z')

    mats = [
        Matrix.Identity(4),
        Rx(90), Rx(-90),
        Ry(90), Ry(-90),
        Rz(90), Rz(-90),
        Rx(90) @ Rz(90),
        Rx(90) @ Rz(-90),
        Ry(90) @ Rz(90),
        Ry(90) @ Rz(-90),
    ]
    mw_orig = obj.matrix_world.copy()
    best = None; best_score = 1e18
    for M in mats:
        obj.matrix_world = M @ mw_orig
        d = world_dims(obj)
        # score: prefer X big, then Y moderate, Z small; penalize non-sorted
        pen = 0.0
        if d.x < d.y: pen += (d.y-d.x)*1000
        if d.y < d.z: pen += (d.z-d.y)*1000
        score = -d.x + 0.1*d.z + pen
        if score < best_score:
            best = M
            best_score = score
    obj.matrix_world = best @ mw_orig
    bpy.context.view_layer.update()

def uniform_fit_wh(obj, target_w, target_h):
    d = world_dims(obj)
    if d.x <= 0 or d.y <= 0:
        return
    s = min(target_w/d.x, target_h/d.y)
    obj.scale *= s
    bpy.context.view_layer.update()

def make_base(width, height, thickness):
    bpy.ops.mesh.primitive_cube_add()
    base = bpy.context.active_object
    base.name = "Base"
    base.scale = (width/2.0, height/2.0, thickness/2.0)
    base.location = (0, 0, thickness/2.0)
    return base

def make_text(txt, size, depth, x, y, z, font_path=""):
    bpy.ops.object.text_add()
    t = bpy.context.active_object
    t.name = "Text_" + txt[:12]
    if font_path and os.path.exists(font_path):
        try:
            t.data.font = bpy.data.fonts.load(font_path)
        except:
            pass
    t.data.body = txt
    t.data.size = size
    t.data.extrude = depth
    t.location = (x, y, z)
    # rotate upright on plate
    t.rotation_euler = (radians(90), 0, 0)
    bpy.context.view_layer.update()
    return t

def export_stl(obj, out_dir, job_id):
    name = obj.name.lower().replace(" ", "_")
    path = os.path.join(out_dir, f"{name}_{job_id}.stl")
    select_only(obj)
    bpy.ops.export_mesh.stl(filepath=path, use_selection=True, ascii=False)
    return path

def save_blend(path):
    bpy.ops.wm.save_as_mainfile(filepath=path)

def dump_layout_json(out_dir, job_id, constants, placed):
    data = {
        "units": "mm",
        "layout": constants,
        "items": placed
    }
    p = os.path.join(out_dir, f"starter_pack_layout_{job_id}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return p

# ----------------------------- main -----------------------------
def main():
    args = parse_args()
    ensure_outdir(args.outdir)

    # Scene
    clear_scene()
    set_units_mm()

    # Constants
    BASE_W = args.base_w
    BASE_H = args.base_h
    BASE_TH = args.base_th
    TEXT_H = args.text_h
    USABLE_H = args.base_h - args.text_h

    FIG_W = args.figure_w
    FIG_H = args.figure_h

    GAP = args.gap
    ACC_SIZE = args.acc_size
    ACC_COUNT = max(0, min(args.acc_count, len(args.accessories)))

    # Derived slots
    FIG_X = -(BASE_W/2 - FIG_W/2)
    FIG_Y = (BASE_H/2 - TEXT_H - USABLE_H) + USABLE_H/2 - FIG_H/2

    ACC_X = FIG_X + FIG_W/2 + GAP + ACC_SIZE/2
    # Even spacing for N cells along usable height
    spacing = USABLE_H / max(1, ACC_COUNT)
    acc_centers = [ (FIG_Y + FIG_H/2) - (ACC_SIZE/2) - i*spacing for i in range(ACC_COUNT) ]

    # Base & text
    base = make_base(BASE_W, BASE_H, BASE_TH)
    title = make_text(args.title, size=14, depth=1.2, x=0, y=(BASE_H/2 - TEXT_H/2), z=BASE_TH+0.5, font_path=args.font)
    subtitle = make_text(args.subtitle, size=7, depth=0.8, x=0, y=(BASE_H/2 - TEXT_H + 12), z=BASE_TH+0.3, font_path=args.font)

    # Figure
    fig = None
    if os.path.exists(args.figure):
        fig, _ = import_model(args.figure, "Figure")
        if fig:
            apply_all_transforms(fig)
            try_orient_longest_X_second_Y(fig)
            center_xy_on_origin(fig)
            rest_on_z0(fig)
            uniform_fit_wh(fig, FIG_W, FIG_H)
            fig.location = (FIG_X, FIG_Y + FIG_H/2, BASE_TH/2)
            apply_all_transforms(fig)

    # Accessories
    acc_objs = []
    for i in range(ACC_COUNT):
        path = args.accessories[i]
        if not os.path.exists(path):
            continue
        acc, _ = import_model(path, f"Accessory_{i+1}")
        if acc:
            apply_all_transforms(acc)
            try_orient_longest_X_second_Y(acc)
            center_xy_on_origin(acc)
            rest_on_z0(acc)
            uniform_fit_wh(acc, ACC_SIZE, ACC_SIZE)
            acc.location = (ACC_X, acc_centers[i], BASE_TH/2)
            apply_all_transforms(acc)
            acc_objs.append(acc)

    # Collect placement info
    placed = []
    for obj in [o for o in [fig] + acc_objs if o]:
        mn, mx = world_aabb(obj)
        dims = world_dims(obj)
        placed.append({
            "name": obj.name,
            "role": "figure" if obj == fig else "accessory",
            "location_mm": [obj.location.x, obj.location.y, obj.location.z],
            "rotation_euler": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
            "scale": list(obj.scale),
            "dimensions_mm": [dims.x, dims.y, dims.z],
            "aabb_world_mm": {"min": list(mn), "max": list(mx)}
        })

    constants = {
        "base": {"w_mm": BASE_W, "h_mm": BASE_H, "th_mm": BASE_TH},
        "text_h_mm": TEXT_H,
        "usable_h_mm": USABLE_H,
        "figure_area_mm": {"w": FIG_W, "h": FIG_H, "x": FIG_X, "y": FIG_Y},
        "accessory": {"size_mm": ACC_SIZE, "x_mm": ACC_X, "spacing_mm": spacing, "count": ACC_COUNT},
        "titles": {"title": args.title, "subtitle": args.subtitle}
    }

    # Save outputs
    blend_path = os.path.join(args.outdir, f"starter_pack_{args.job_id}.blend")
    save_blend(blend_path)

    if args.export_stl:
        if fig: export_stl(fig, args.outdir, args.job_id)
        for o in acc_objs:
            export_stl(o, args.outdir, args.job_id)

    json_path = dump_layout_json(args.outdir, args.job_id, constants, placed)
    print(f"[OK] Saved: {blend_path}")
    print(f"[OK] Layout JSON: {json_path}")

if __name__ == "__main__":
    main()
