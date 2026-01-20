# starter_pack_card_layout.py
# One-file Blender script: orient, layout, and export a rounded-card STL
# Blender 3.x / 4.x

import struct
import bpy, bmesh, os, sys, math, argparse, json
from math import radians
from math import degrees
from mathutils import Vector, Matrix

# ----------------------------- CLI -----------------------------
def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--")+1:]
    p = argparse.ArgumentParser(description="Starter Pack card layout")
    # Inputs
    p.add_argument("--figure", required=True, help="Path to main figure (glb/gltf/obj/stl)")
    p.add_argument("--acc", nargs="*", default=[], help="Up to 3 accessory file paths")
    # Card & layout
    p.add_argument("--card_width", type=float, required=True, help="Card width (mm)")
    p.add_argument("--card_height", type=float, required=True, help="Card height (mm)")
    p.add_argument("--card_thickness", type=float, required=True, help="Card thickness (mm)")
    p.add_argument("--upper_ratio", type=float, default=0.25, help="Upper band ratio of card_height (e.g., 0.25 for card_height/4)")
    p.add_argument("--margin_accessories", type=float, default=2.0, help="Accessory margin (mm) inside each accessory slot")
    p.add_argument("--margin_figure", type=float, default=4.0, help="Figure margin (mm) inside figure slot")
    p.add_argument("--padding_card", type=float, default=4.0, help="Card Padding (mm)")
    p.add_argument("--T", type=float, default=0.0, help="Target top-face Z above ground (mm) after placement")
    p.add_argument("--fillet", type=float, default=5.0, help="Card corner fillet radius (mm)")
    # Orientation overrides (optional)
    p.add_argument("--flip_head", action="store_true", help="Flip main figure 'head' direction (swap +Y/-Y)")
    p.add_argument("--acc_front_up", action="store_true", help="Rotate accessories so their 'front' faces +Y (best-effort)")
    # Output
    p.add_argument("--outdir", required=True, help="Output folder")
    p.add_argument("--middir", required=True, help="Middle Output folder")
    p.add_argument("--job_id", default="run", help="Job id for filenames")
    p.add_argument("--save_blend", action="store_true", help="Also save a .blend for inspection")
    p.add_argument("--title",      type=str, default="Starter Pack")
    p.add_argument("--subtitle",   type=str, default="By M3D")
    p.add_argument("--TS",         type=float, default=14.0,  help="Title font size X (Blender text size)")
    p.add_argument("--MT",         type=float, default=0.0,   help="Vertical margin between title and subtitle")
    p.add_argument("--TH",         type=float, default=20.0,  help="Target total height (Y-extent) of the two-line group")
    p.add_argument("--font",       type=str,   default="",     help="Optional TTF/OTF path for both texts")
    p.add_argument("--text_extr",  type=float, default=0.8,   help="Text extrusion (depth in Z)")
    p.add_argument("--text_lift",  type=float, default=-0.2,   help="Lift above card top to avoid z-fighting")
    #Keyhole
    p.add_argument("--has_hole", action="store_true", help="If set, cut a key hole through the card")
    p.add_argument("--hole_d", type=float, default=6.0, help="Key hole diameter (mm)")
    p.add_argument("--hole_margin", type=float, default=4.0, help="Inset from card edges (mm)")
    p.add_argument("--hole_corner", type=str, default="top_right", choices=["top_right","top_left","bottom_right","bottom_left"])
    p.add_argument("--model_name_seed", type=str, default="card", choices=["card", "keychain"])
    
    # render with Texture
    p.add_argument("--render_resx", type=int, default=1920, help="Render resolution X")
    p.add_argument("--render_resy", type=int, default=1080, help="Render resolution Y")

    args = p.parse_args(argv)
    # Limit accessories to 3 as requested
    args.acc = list(args.acc[:3])
    return args
    
# (Assumes you already have robust world_aabb(obj) and world_dims(obj))
def ensure_linked(obj):
    if not getattr(obj, "users_collection", None):
        bpy.context.scene.collection.objects.link(obj)
    elif bpy.context.scene.collection not in obj.users_collection:
        bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()


def diagnose_text_group_front(text_group, px=1600, margin=0.08):
    import bpy, math
    from mathutils import Vector, Matrix

    def vfmt(v): return f"({v.x:.4f}, {v.y:.4f}, {v.z:.4f})"

    print("=== DIAG: text_group front render ===")
    print(f"group: {text_group.name if text_group else None}")

    if not text_group:
        print("!! group is None")
        return

    bpy.context.view_layer.update()

    # collect kids (and show all)
    kids_all = list(text_group.children)
    kids = [c for c in kids_all if getattr(c, "type", "") in {"FONT", "CURVE", "MESH"}]
    print(f"children total: {len(kids_all)}, renderable: {len(kids)} [{', '.join(c.type for c in kids)}]")

    if not kids:
        print("!! No renderable children (FONT/CURVE/MESH).")
        return

    deps = bpy.context.evaluated_depsgraph_get()

    # per-child dump
    for i, ch in enumerate(kids, 1):
        print(f"\n-- child #{i}: {ch.name} type={ch.type} hide_render={ch.hide_render}")
        # evaluated mesh verts (if any)
        verts = None
        try:
            eo = ch.evaluated_get(deps)
            me = None
            try:
                me = bpy.data.meshes.new_from_object(eo, depsgraph=deps)
            except Exception:
                me = None
            if me:
                verts = len(me.vertices)
                bpy.data.meshes.remove(me)
        except Exception as e:
            print(f"  [warn] evaluated_get failed: {e}")

        if verts is not None:
            print(f"  eval mesh verts: {verts}")
        else:
            print("  eval mesh verts: <none> (FONT/CURVE may still render via curve tessellation)")

        # AABB
        try:
            mn, mx = world_aabb(ch)
            size = mx - mn
            print(f"  AABB mn={vfmt(mn)} mx={vfmt(mx)} size=({size.x:.4f},{size.y:.4f},{size.z:.4f})")
        except Exception as e:
            print(f"  [err] world_aabb failed: {e}")

        # local -Y in world
        try:
            fwd = (ch.matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0)))
            print(f"  local(-Y)->world = {vfmt(fwd)} len={fwd.length:.6f}")
        except Exception as e:
            print(f"  [err] local -Y => world failed: {e}")

        # text params (if FONT)
        if ch.type == "FONT":
            try:
                print(f"  FONT size={getattr(ch.data,'size',None)} extrude={getattr(ch.data,'extrude',None)}")
            except Exception:
                pass

    # union AABB across kids
    from mathutils import Vector
    mn = Vector((+1e30, +1e30, +1e30))
    mx = Vector((-1e30, -1e30, -1e30))
    for ch in kids:
        try:
            a, b = world_aabb(ch)
            mn.x = min(mn.x, a.x); mn.y = min(mn.y, a.y); mn.z = min(mn.z, a.z)
            mx.x = max(mx.x, b.x); mx.y = max(mx.y, b.y); mx.z = max(mx.z, b.z)
        except Exception as e:
            print(f"[warn] skip AABB for {ch.name}: {e}")
    center = (mn + mx) * 0.5
    size = mx - mn
    print("\n== UNION AABB ==")
    print(f"mn={vfmt(mn)} mx={vfmt(mx)} size=({size.x:.4f},{size.y:.4f},{size.z:.4f})")

    if size.x <= 1e-9 and size.y <= 1e-9 and size.z <= 1e-9:
        print("!! Union AABB is basically a point — nothing to render.")
        return

    # Camera basis: make camera -Z == front
    ref = kids[0]
    fwd = (ref.matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0))).normalized()
    if not math.isfinite(fwd.length) or fwd.length <= 1e-9:
        print("!! Bad forward vector from ref child's local -Y.")
        return
    up_world = Vector((0, 0, 1))
    right = up_world.cross(fwd)
    if right.length_squared == 0.0:
        up_world = Vector((0, 1, 0))
        right = up_world.cross(fwd)
    right.normalize()
    up_cam = fwd.cross(right).normalized()

    M_cam = Matrix((
        ( right.x,  up_cam.x,  -fwd.x,  center.x + fwd.x*2.0 ),
        ( right.y,  up_cam.y,  -fwd.y,  center.y + fwd.y*2.0 ),
        ( right.z,  up_cam.z,  -fwd.z,  center.z + fwd.z*2.0 ),
        (   0.0,      0.0,       0.0,         1.0           ),
    ))
    Cinv = M_cam.inverted()
    print("\n== CAMERA BASIS ==")
    print(f"right={vfmt(Vector((M_cam[0][0], M_cam[1][0], M_cam[2][0])))}")
    print(f"up   ={vfmt(Vector((M_cam[0][1], M_cam[1][1], M_cam[2][1])))}")
    print(f"-fwd ={vfmt(Vector((M_cam[0][2], M_cam[1][2], M_cam[2][2])))}")
    print(f"pos  ={vfmt(Vector((M_cam[0][3], M_cam[1][3], M_cam[2][3])))}")
    print(f"px target={px}  margin={margin}")

    # Project union bbox and measure
    corners = [Vector((x, y, z)) for x in (mn.x, mx.x) for y in (mn.y, mx.y) for z in (mn.z, mx.z)]
    pts = [Cinv @ p for p in corners]
    min_u = min(p.x for p in pts); max_u = max(p.x for p in pts)
    min_v = min(p.y for p in pts); max_v = max(p.y for p in pts)
    w_proj = max_u - min_u
    h_proj = max_v - min_v
    print("\n== PROJECTION ==")
    print(f"proj w={w_proj:.6f} h={h_proj:.6f}")

    # Fallback analytic projection via axis dot-products
    X = Vector((M_cam[0][0], M_cam[1][0], M_cam[2][0]))  # cam X in world
    Y = Vector((M_cam[0][1], M_cam[1][1], M_cam[2][1]))  # cam Y in world
    projs = [((p - center).dot(X), (p - center).dot(Y)) for p in corners]
    xs = [u for (u, v) in projs]; ys = [v for (u, v) in projs]
    w_alt = max(xs) - min(xs); h_alt = max(ys) - min(ys)
    print(f"alt  w={w_alt:.6f} h={h_alt:.6f}")

    if w_proj <= 1e-9 or h_proj <= 1e-9:
        print("!! Degenerate projected size. If alt is OK, math pipeline is fine—camera linking step may be wrong.")
    if w_alt <= 1e-9 or h_alt <= 1e-9:
        print("!! Even alt sizes are zero — union AABB is flat along a camera axis or children truly have zero extent.")

def render_text_group_front_png(text_group, out_png_path, px=1600, margin=0.08, color=(1,0,0,1)):
    """
    Render 'text_group' (an Empty with FONT children) as a single PNG:
      - Orthographic, top-down (camera looks along world -Z)
      - Solid flat color (emission) on all text children
      - Transparent background
      - Tight crop with 'margin' fraction around the union bounds
    """
    import bpy
    from mathutils import Vector, Matrix

    bpy.context.view_layer.update()

    # 1) Collect renderable children (FONT/CURVE/MESH)
    kids = [c for c in text_group.children if getattr(c, "type", "") in {"FONT", "CURVE", "MESH"}]
    if not kids:
        print("[WARN] render_text_group_front_png: group has no renderable children; skipping.")
        return

    # 2) Hide everything else
    all_objs = list(bpy.data.objects)
    prev_hide = {o: o.hide_render for o in all_objs}
    for o in all_objs:
        o.hide_render = True
    for o in kids:
        o.hide_render = False

    # 3) Assign solid flat color (emission) to each child
    mat_name = "_TMP_TextSolidColor"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em  = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (float(color[0]), float(color[1]), float(color[2]), float(color[3]))
        em.inputs["Strength"].default_value = 1.0
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    for ch in kids:
        data = getattr(ch, "data", None)
        if not data:
            continue
        if len(ch.material_slots) == 0:
            data.materials.append(mat)
        else:
            for i in range(len(ch.material_slots)):
                ch.material_slots[i].material = mat

    bpy.context.view_layer.update()

    # 4) Union AABB of kids in WORLD space
    mn = Vector((+1e30, +1e30, +1e30))
    mx = Vector((-1e30, -1e30, -1e30))
    for ch in kids:
        a, b = world_aabb(ch)  # your existing robust AABB
        mn.x = min(mn.x, a.x); mn.y = min(mn.y, a.y); mn.z = min(mn.z, a.z)
        mx.x = max(mx.x, b.x); mx.y = max(mx.y, b.y); mx.z = max(mx.z, b.z)
    center = (mn + mx) * 0.5

    # 5) Camera: orthographic TOP-DOWN (camera looks along world -Z)
    cam = bpy.data.objects.get("_TMP_TextCamGroup")
    if not cam:
        cam_data = bpy.data.cameras.new("_TMP_TextCamGroup")
        cam = bpy.data.objects.new("_TMP_TextCamGroup", cam_data)
        bpy.context.scene.collection.objects.link(cam)
    cam.data.type = 'ORTHO'

    # Build camera matrix: local axes in world
    # right = +X_world, up = +Y_world, forward = -Z_world (camera looks along local -Z)
    right = Vector((1, 0, 0))
    up    = Vector((0, 1, 0))
    fwd   = Vector((0, 0, -1))       # desired viewing direction
    dist  = 20.0                      # any positive; ortho ignores perspective
    cam.matrix_world = Matrix((
        ( right.x, up.x,  0.0, center.x              ),
        ( right.y, up.y,  0.0, center.y              ),
        ( right.z, up.z,  1.0, center.z + dist       ),  # local +Z points up; camera looks along local -Z
        (   0.0,    0.0,  0.0, 1.0                   ),
    ))

    # 6) Compute ortho scale from union bbox projected into the camera plane (X–Y)
    # Since we are top-down, the image axes are world X (width) and world Y (height)
    w = (mx.x - mn.x)
    h = (mx.y - mn.y)
    if w <= 1e-9 or h <= 1e-9:
        print("[WARN] render_text_group_front_png: zero XY bounds; skipping render.")
        for o, hflag in prev_hide.items(): o.hide_render = hflag
        return

    w *= (1.0 + margin * 2.0)
    h *= (1.0 + margin * 2.0)
    cam.data.ortho_scale = max(w, h)

    # 7) Render settings
    sc = bpy.context.scene
    sc.camera = cam
    aspect = w / h
    if aspect >= 1.0:
        sc.render.resolution_x = px
        sc.render.resolution_y = max(1, int(round(px / aspect)))
    else:
        sc.render.resolution_y = px
        sc.render.resolution_x = max(1, int(round(px * aspect)))

    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.render.film_transparent = True
    abs_path = bpy.path.abspath(out_png_path)  # expands // relative to blend/file
    abs_path = os.path.abspath(abs_path)       # OS-absolute
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    sc.render.filepath = abs_path

    # 8) Render
    bpy.ops.render.render(write_still=True)

    # 9) Restore visibility
    for o, hflag in prev_hide.items():
        o.hide_render = hflag

    print(f"[OK] Text group top-down rendered → {out_png_path}")


# --- solid material (red by default), emission for flat color ---
def ensure_solid_mat(name="TextSolidRed", rgba=(1.0,0.0,0.0,1.0), emission=True, strength=1.0):
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if emission:
        sh = nt.nodes.new("ShaderNodeEmission")
        sh.inputs["Color"].default_value = rgba
        sh.inputs["Strength"].default_value = strength
    else:
        sh = nt.nodes.new("ShaderNodeBsdfPrincipled")
        sh.inputs["Base Color"].default_value = rgba
        sh.inputs["Roughness"].default_value = 1.0
        sh.inputs["Metallic"].default_value = 0.0
    nt.links.new(sh.outputs[0], out.inputs["Surface"])
    return mat


def make_text(txt, size, extrude, font_path="", roll_deg=0.0):
    """
    Create a FONT object, link it, and rotate it so it faces up (+90° about X)
    plus an extra roll 'roll_deg' about the same X-parallel axis through its center.
    """
    cu = bpy.data.curves.new(name=f"TXT_{txt[:24]}", type='FONT')
    cu.body    = txt
    cu.size    = float(size)
    cu.extrude = float(extrude)

    if font_path and os.path.exists(font_path):
        try:
            cu.font = bpy.data.fonts.load(font_path)
        except Exception as e:
            print(f"[make_text] Font load failed: {e}")

    ob = bpy.data.objects.new(cu.name, cu)
    ensure_linked(ob)

    # Face up (+90° about X), then add extra roll about X
    ob.rotation_mode = 'XYZ'
    ob.rotation_euler = (radians(90.0 + float(roll_deg)), 0.0, 0.0)

    bpy.context.view_layer.update()
    return ob
    
def union_aabb(objs):
    """World-space AABB of a list of objects."""
    mn = Vector((+1e30, +1e30, +1e30))
    mx = Vector((-1e30, -1e30, -1e30))
    for o in objs:
        a,b = world_aabb(o)
        mn.x = min(mn.x, a.x); mn.y = min(mn.y, a.y); mn.z = min(mn.z, a.z)
        mx.x = max(mx.x, b.x); mx.y = max(mx.y, b.y); mx.z = max(mx.z, b.z)
    return mn, mx

def union_center(objs):
    mn, mx = union_aabb(objs)
    return (mn + mx) * 0.5

def place_sub_below_title(title_obj, sub_obj, margin_MT):
    """
    Vertically stack: title above, subtitle below with margin_MT in Y.
    Objects are assumed already rotated to face up (X-rot = 90°).
    Centers both on X. Keeps current Z (we'll lift to card later).
    """
    # center X for both
    for o in (title_obj, sub_obj):
        mn, mx = world_aabb(o)
        cx = 0.5*(mn.x + mx.x)
        o.location.x -= cx

    # compute current Y extents
    t_mn, t_mx = world_aabb(title_obj)
    s_mn, s_mx = world_aabb(sub_obj)
    t_h = t_mx.y - t_mn.y
    s_h = s_mx.y - s_mn.y

    # place title so its center is at Y = + (s_h + margin)/2
    # and subtitle so its center is at Y = - (t_h + margin)/2
    title_center_y = +0.5*(s_h + margin_MT)
    sub_center_y   = -0.5*(t_h + margin_MT)

    # shift each to target center while preserving own center offset
    def shift_to_center_y(o, target_cy):
        mn, mx = world_aabb(o)
        cy = 0.5*(mn.y + mx.y)
        o.location.y += (target_cy - cy)

    shift_to_center_y(title_obj, title_center_y)
    shift_to_center_y(sub_obj,   sub_center_y)
    bpy.context.view_layer.update()

def group_under_empty(objs, name="TextGroup"):
    """Create an Empty and parent objs to it (keep transforms)."""
    empty = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(empty)
    # place empty at union center
    c = union_center(objs)
    empty.location = c
    bpy.context.view_layer.update()

    # parent with KEEP transform
    for o in objs:
        o.parent = empty
        o.matrix_parent_inverse = empty.matrix_world.inverted()

    return empty

def scale_group_y_to_height(group_root, children, target_height, slot_bottom_y, slot_top_y):
    """
    Uniformly scale the group so union Y-size == min(target_height, slot_height).
    Then center it inside the slot in Y. Scaling is about union center.
    """
    slot_h = max(1e-6, float(slot_top_y - slot_bottom_y))
    mn, mx = union_aabb(children)
    cur_h = float(mx.y - mn.y)
    if cur_h < 1e-9:
        return  # nothing to do

    desired_h = min(float(target_height), slot_h)
    s = desired_h / cur_h

    # scale about union center (world)
    c = union_center(children)
    T = Matrix.Translation(c)
    S = Matrix.Scale(s, 4)  # uniform
    group_root.matrix_world = T @ S @ T.inverted() @ group_root.matrix_world
    bpy.context.view_layer.update()

    # recalc AABB after scaling, then center in Y within slot
    mn, mx = union_aabb(children)
    cy = 0.5*(mn.y + mx.y)
    slot_cy = 0.5*(slot_bottom_y + slot_top_y)
    group_root.location.y += (slot_cy - cy)
    bpy.context.view_layer.update()

def sink_into_card(obj, card_obj, max_fraction=1.0/3.0):
    """
    Push the object down into the card, but not more than 'max_fraction' of the object's height.
    Assumes the object is already snapped so its bottom touches the card top (Z=0 for the card).
    """
    # card top/bottom
    card_top = world_aabb(card_obj)[1].z      # should be 0 after our setup
    card_bottom = world_aabb(card_obj)[0].z   # -thickness

    # object size
    d = world_dims(obj)
    obj_h = float(d.z)
    if obj_h <= 0.0:
        return

    # max allowed sink
    max_sink = obj_h * float(max_fraction)
    # cannot sink past card bottom plane (that would fully embed); cap by card thickness
    card_th = card_top - card_bottom
    sink = min(max_sink, card_th)

    # ensure current bottom is at card top (touching) before sinking
    cur_bottom = bottom_z(obj)
    dz_to_touch = card_top - cur_bottom
    obj.location.z += dz_to_touch

    # now sink by 'sink'
    obj.location.z -= sink
    bpy.context.view_layer.update()
    
def snap_bottom_to_base_top(obj, base_obj, z_offset: float = 0.0):
    """
    Move 'obj' along Z so its *bottom* (minZ) sits exactly on the *top* (maxZ)
    of 'base_obj', plus an optional z_offset (gap). Positive z_offset lifts it.
    """
    target = top_z(base_obj) + float(z_offset)
    dz = target - bottom_z(obj)
    obj.location.z += dz
    bpy.context.view_layer.update()

# THis is not used anymore. Will make the object stay right on top of the card
def lift_group_to_card_top(group_root, children, card_obj, lift=0.2):
    """Place the group to sit on card top with an extra tiny lift."""
    # put Z so bottom touches card top, then add lift
    # find current bottoms of children and top of card
    card_top = world_aabb(card_obj)[1].z
    mn, _ = union_aabb(children)
    cur_bottom = float(mn.z)
    dz = (card_top + float(lift)) - cur_bottom
    group_root.location.z += dz
    bpy.context.view_layer.update()


# ----------------------------- scene setup -----------------------------
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def set_units_mm():
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 0.001  # numbers are mm

def ensure_outdir(p):
    os.makedirs(p, exist_ok=True)

def ensure_middir(p):
    os.makedirs(p, exist_ok=True)

def select_only(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def apply_xforms(obj):
    select_only(obj)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# ----------------------------- import -----------------------------
def import_model(path, name_hint):
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
    # pick largest mesh
    meshes = [o for o in new if o.type=='MESH']
    root = None
    if meshes:
        meshes.sort(key=lambda o: (len(o.data.vertices), o.dimensions.x*o.dimensions.y*o.dimensions.z), reverse=True)
        root = meshes[0]
    else:
        root = new[0] if new else None
    if root:
        root.name = name_hint
    return root

# ----------------------------- geometry helpers -----------------------------
def world_aabb(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    M = eo.matrix_world
    pts = [M @ Vector(c) for c in eo.bound_box]
    xs = [p.x for p in pts]; ys=[p.y for p in pts]; zs=[p.z for p in pts]
    mn = Vector((min(xs),min(ys),min(zs)))
    mx = Vector((max(xs),max(ys),max(zs)))
    return mn, mx

def world_dims(obj):
    mn, mx = world_aabb(obj)
    return mx - mn

def center_xy(obj):
    mn, mx = world_aabb(obj)
    cx = 0.5*(mn.x+mx.x); cy=0.5*(mn.y+mx.y)
    obj.location.x -= cx; obj.location.y -= cy
    bpy.context.view_layer.update()

def rest_on_z0(obj):
    mn, mx = world_aabb(obj)
    obj.location.z -= mn.z
    bpy.context.view_layer.update()

def set_top_to(obj, target_top_z):
    mn, mx = world_aabb(obj)
    dz = target_top_z - mx.z
    obj.location.z += dz
    bpy.context.view_layer.update()

# --- vertical snapping: make object just touch the card's top face ---
def top_z(obj):
    _, mx = world_aabb(obj)
    return float(mx.z)

def bottom_z(obj):
    mn, _ = world_aabb(obj)
    return float(mn.z)


import math
import bpy

def uniform_fit(obj, target_w, target_h, margin=0.0, target_d=None):
    """
    Uniformly scale 'obj' so it fits within (target_w x target_h) minus margin on all sides.
    If target_d is provided, it also fits the third dimension (depth) using the same uniform scale.
    Returns the final world-space depth (Z-size) after scaling.

    Args:
        obj        : Blender object
        target_w   : target width (X)
        target_h   : target height (Y)
        margin     : margin applied on each side (applies to card_width, card_height, and D if target_d given)
        target_d   : optional target depth (Z). If provided, included in the fit.

    Returns:
        float: final world-depth (Z extent) after scaling
    """
    eps = 1e-9
    d = world_dims(obj)  # uses your robust world_dims()
    if d.x < eps or d.y < eps or (target_d is not None and d.z < eps):
        # Nothing sensible to scale; return current depth
        return float(d.z)

    tw = max(1e-6, float(target_w) - 2.0 * margin)
    th = max(1e-6, float(target_h) - 2.0 * margin)

    scales = [tw / max(d.x, eps), th / max(d.y, eps)]
    if target_d is not None:
        td = max(1e-6, float(target_d))
        scales.append(td / max(d.z, eps))

    s = min(scales)
    if not math.isfinite(s) or s <= 0:
        s = 1.0

    obj.scale *= s
    bpy.context.view_layer.update()

    # Return final depth (world Z extent) after scaling
    final_depth = float(world_dims(obj).z)
    return final_depth


def world_sizes(obj):
    mn, mx = world_aabb(obj)
    d = mx - mn
    return Vector((float(d.x), float(d.y), float(d.z)))

def world_center(obj):
    mn, mx = world_aabb(obj)
    return (mn + mx) * 0.5

# ---------- 1) CHECK: does this object want a 90° roll about global X? ----------
def needs_x_roll(obj) -> bool:
    """
    Returns True if size along global Y is LESS than size along global Z.
    (i.e., it's 'taller' than it is 'long' in Y, so lay it on its back)
    """
    dx, dy, dz = world_sizes(obj)
    return dy < dz

# ----- rotate about an axis parallel to world X, through object center -----
def roll_about_parallel_world_x(obj, degrees: float = 90.0):
    """
    Rotate obj by +degrees about an axis that is PARALLEL to world X
    and passes through the object's WORLD-SPACE center.
    (i.e., same direction as global X, pivoted at object's center)
    """
    c = world_center(obj)                            # pivot in world coords
    T = Matrix.Translation(c)
    R = Matrix.Rotation(radians(degrees), 4, 'X')    # axis parallel to world X
    obj.matrix_world = T @ R @ T.inverted() @ obj.matrix_world
    bpy.context.view_layer.update()

# ----------------------------- card geometry -----------------------------
def create_rounded_card(width, height, thickness, radius):
    """
    Make a rounded rectangle plate centered on origin.
    TOP at Z=0 (ground plane), thickness extrudes downward to Z=-thickness.
    """
    import bmesh
    from mathutils import Vector

    # Clamp radius to avoid self-intersections
    rmax = max(0.0, min(width, height) * 0.5 - 0.01)
    radius = max(0.0, min(radius, rmax))

    bm = bmesh.new()

    # 1) Base rectangle face at Z=0
    dx = width * 0.5
    dy = height * 0.5
    v0 = bm.verts.new(Vector((-dx, -dy, 0.0)))
    v1 = bm.verts.new(Vector(( dx, -dy, 0.0)))
    v2 = bm.verts.new(Vector(( dx,  dy, 0.0)))
    v3 = bm.verts.new(Vector((-dx,  dy, 0.0)))
    bm.faces.new((v0, v1, v2, v3))
    bm.normal_update()

    # 2) Bevel corners to get rounded rectangle
    geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    bmesh.ops.bevel(
        bm,
        geom=geom,
        offset=radius,
        segments=8,
        profile=0.5,
        affect='VERTICES',
        offset_type='OFFSET'
    )

    # IMPORTANT: refresh lookup tables after topology ops
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    # 3) Pick all faces that lie on the top plane (Z ~ 0) and extrude them downward
    top_faces = []
    for f in bm.faces:
        # if all verts are very close to Z=0, treat as top face
        if all(abs(v.co.z) < 1e-7 for v in f.verts):
            top_faces.append(f)
    if not top_faces:
        # fallback: take the largest face
        top_faces = [max(bm.faces, key=lambda F: F.calc_area())]

    ret = bmesh.ops.extrude_face_region(bm, geom=top_faces)
    new_geom = ret["geom"]
    new_verts = [ele for ele in new_geom if isinstance(ele, bmesh.types.BMVert)]

    # Move the extruded shell down by thickness (so top remains at Z=0)
    bmesh.ops.translate(bm, verts=new_verts, vec=Vector((0.0, 0.0, -thickness)))

    # 4) Build mesh object
    me = bpy.data.meshes.new("CardMesh")
    bm.to_mesh(me)
    bm.free()

    card = bpy.data.objects.new("Card", me)
    bpy.context.scene.collection.objects.link(card)
    return card

def create_beveled_card(width, height, thickness, fillet_radius, name="Card"):
    """
    Creates a rectangular card from a cube and applies a Bevel modifier to edges.
    Card is centered on XY; TOP is at Z=0, thickness extends to Z=-thickness.
    """
    # Add a unit cube then scale to size/2 (since cube scale is from center)
    bpy.ops.mesh.primitive_cube_add()
    card = bpy.context.active_object
    card.name = name

    # scale (from center) so final extents are width x height x thickness
    card.scale = (width/2.0, height/2.0, thickness/2.0)
    # put top at Z=0, bottom at Z=-thickness
    card.location.z = thickness/2.0 * 1.0  # after scaling, top will be at +th/2
    # shift down by +th/2 so top becomes 0
    card.location.z -= thickness/2.0

    # bevel modifier (vertex mode gives nice round corners)
    bev = card.modifiers.new(name="CardBevel", type='BEVEL')
    bev.limit_method = 'ANGLE'
    if hasattr(bev, "angle_limit"):
        bev.angle_limit = math.radians(60.0)
    elif hasattr(bev, "angle"):      # older builds
        bev.angle = math.radians(60.0)
    bev.profile = 0.5
    bev.segments = 3
    bev.width = max(0.0, float(fillet_radius))
    bev.affect = 'VERTICES'  # round the 4 corners

    # apply transforms & bevel
    bpy.context.view_layer.update()
    select_only(card)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.modifier_apply(modifier=bev.name)

    return card

def cut_key_hole(card_obj, card_w, card_h, card_th, hole_d=6.0, hole_margin=4.0, corner="top_right"):
    """
    Boolean-cut a cylindrical hole that fully pierces the card.
    Hole center is inset by 'hole_margin' from chosen corner.
    """
    r = float(hole_d) * 0.5
    # choose corner
    x = +card_w/2.0 - hole_margin
    y = +card_h/2.0 - hole_margin
    if corner == "top_left":     x = -card_w/2.0 + hole_margin; y = +card_h/2.0 - hole_margin
    if corner == "bottom_right": x = +card_w/2.0 - hole_margin; y = -card_h/2.0 + hole_margin
    if corner == "bottom_left":  x = -card_w/2.0 + hole_margin; y = -card_h/2.0 + hole_margin

    # add tall cylinder so it surely spans thickness
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=r, depth=card_th*2.5, location=(x, y, -card_th*0.5))
    cutter = bpy.context.active_object
    cutter.name = "_KeyHoleCutter"

    # boolean difference
    bool_mod = card_obj.modifiers.new(name="KeyHole", type='BOOLEAN')
    bool_mod.operation = 'DIFFERENCE'
    bool_mod.solver = 'EXACT'
    bool_mod.object = cutter

    select_only(card_obj)
    bpy.ops.object.modifier_apply(modifier=bool_mod.name)

    # clean up cutter
    bpy.data.objects.remove(cutter, do_unlink=True)


def obj_xy_aabb(obj):
    """Return (minx, miny, maxx, maxy) AABB for a single object in world space."""
    mn, mx = world_aabb(obj)
    return float(mn.x), float(mn.y), float(mx.x), float(mx.y)

def group_xy_aabb(children):
    """Return AABB for a list of objects (e.g., the text group)."""
    mn, mx = union_aabb(children)
    return float(mn.x), float(mn.y), float(mx.x), float(mx.y)

def pack_xy_record(name, minx, miny, maxx, maxy, rot_z_rad=0.0):
    cx = 0.5*(minx + maxx)
    cy = 0.5*(miny + maxy)
    w  = (maxx - minx)
    h  = (maxy - miny)
    return {
        "name": name,
        "center": {"x": cx, "y": cy},
        "size":   {"w": w,  "h": h},
        "rotation_z_deg": float(degrees(rot_z_rad)),
    }

def write_layout_json(path, meta, records):
    payload = {"meta": meta, "items": records}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OK] Layout JSON: {path}")
    
_GEOM_TYPES = {"MESH", "CURVE", "FONT", "SURFACE"}  # what we want in STL

def _make_temp_mesh_from_obj(obj):
    """Create a temp MESH object from any object (FONT/CURVE/SURFACE/MESH) using evaluated geometry."""
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)

    # get evaluated mesh (works for mesh/curve/font/surface with geometry settings)
    me_eval = eo.to_mesh()
    if not me_eval:
        return None

    # copy into a real datablock we can link
    me_real = bpy.data.meshes.new(obj.name + "_TmpMesh")
    me_real.from_mesh(me_eval)
    eo.to_mesh_clear()

    tmp = bpy.data.objects.new(obj.name + "_Tmp", me_real)
    # keep world transform so geometry lands where you see it
    tmp.matrix_world = eo.matrix_world.copy()
    bpy.context.scene.collection.objects.link(tmp)
    return tmp

def _collect_export_objects_with_temps():
    """Collect all meshes + temp meshes for curves/fonts/surfaces; returns (export_objs, temps_to_delete)."""
    export_objs = []
    temps = []
    for o in bpy.data.objects:
        if o.type == "MESH":
            export_objs.append(o)
        elif o.type in {"CURVE", "FONT", "SURFACE"}:
            t = _make_temp_mesh_from_obj(o)
            if t:
                export_objs.append(t)
                temps.append(t)
    return export_objs, temps

def _cleanup_temps(temps):
    for t in temps:
        try:
            me = t.data
            bpy.data.objects.remove(t, do_unlink=True)
            if me.users == 0:
                bpy.data.meshes.remove(me, do_unlink=True)
        except Exception:
            pass

def _enable_stl_addon() -> bool:
    try:
        import addon_utils
        for modname in ("io_mesh_stl", "io_scene_stl"):
            for m in addon_utils.modules():
                if m.__name__ == modname:
                    addon_utils.enable(modname, default_set=False, persistent=False)
                    return True
            try:
                bpy.ops.preferences.addon_enable(module=modname)
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False

def _try_addon_export_stl(path_stl: str) -> bool:
    """Try official add-on export, including Text/Curves via temp meshes. Returns True on success."""
    if not _enable_stl_addon():
        return False

    export_objs, temps = _collect_export_objects_with_temps()
    if not export_objs:
        _cleanup_temps(temps)
        raise RuntimeError("No geometry to export.")

    # select only our export set
    bpy.ops.object.select_all(action='DESELECT')
    for o in export_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = export_objs[0]

    try:
        # operator name is standard when add-on is present
        if hasattr(bpy.ops, "export_mesh") and hasattr(bpy.ops.export_mesh, "stl"):
            bpy.ops.export_mesh.stl(filepath=path_stl, use_selection=True, ascii=False)
            print(f"[OK] Combined STL (add-on): {path_stl}")
            return True
        return False
    except Exception as e:
        print(f"[WARN] STL add-on export failed: {e}")
        return False
    finally:
        _cleanup_temps(temps)

def _iter_world_tris_any(obj):
    """Yield world-space triangles (v0,v1,v2) for any supported object via evaluated mesh."""
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    me = eo.to_mesh()
    try:
        if not me:
            return
        me.calc_loop_triangles()
        verts = me.vertices
        M = eo.matrix_world
        for tri in me.loop_triangles:
            v0 = M @ verts[tri.vertices[0]].co
            v1 = M @ verts[tri.vertices[1]].co
            v2 = M @ verts[tri.vertices[2]].co
            yield (v0, v1, v2)
    finally:
        eo.to_mesh_clear()

def _write_binary_stl_all(path_stl: str):
    """Addon-free writer that includes Mesh/Text/Curves/Surface."""
    objs = [o for o in bpy.data.objects if o.type in _GEOM_TYPES]
    if not objs:
        raise RuntimeError("No geometry objects to export (MESH/CURVE/FONT/SURFACE).")

    # Count triangles
    tri_count = 0
    for o in objs:
        for _ in _iter_world_tris_any(o):
            tri_count += 1

    with open(path_stl, "wb") as f:
        f.write(b"Generated by Blender script".ljust(80, b"\0"))
        f.write(struct.pack("<I", tri_count))
        for o in objs:
            for v0, v1, v2 in _iter_world_tris_any(o):
                n = (v1 - v0).cross(v2 - v0)
                ln = n.length
                if ln > 1e-20: n /= ln
                else:          n = Vector((0.0, 0.0, 0.0))
                f.write(struct.pack(
                    "<12fH",
                    float(n.x), float(n.y), float(n.z),
                    float(v0.x), float(v0.y), float(v0.z),
                    float(v1.x), float(v1.y), float(v1.z),
                    float(v2.x), float(v2.y), float(v2.z),
                    0
                ))
    print(f"[OK] Combined STL (addon-free): {path_stl}")

def export_scene_as_stl(path_stl: str):
    """First try official add-on (including text/curves via temp meshes), else fallback to built-in writer."""
    if _try_addon_export_stl(path_stl):
        return
    _write_binary_stl_all(path_stl)
# --- end exporter ---

# render scene

# Add new functions for texture-aware import and rendering:
def import_model_with_textures(path, name_hint):
    """Import model with textures from GLB/GLTF"""
    before = set(bpy.context.scene.objects)
    ext = os.path.splitext(path)[1].lower()
    
    # Store current settings
    prev_use_nodes = {}
    for mat in bpy.data.materials:
        prev_use_nodes[mat.name] = mat.use_nodes
    
    if ext in (".glb", ".gltf"):
        # Set import settings to preserve materials and textures
        # Note: GLTF import settings vary by Blender version
        try:
            # For newer Blender versions (3.0+)
            import_settings = {
                'import_shading': 'NORMALS',  # or 'VERTEX_COLORS'
                'merge_vertices': False,
                'bone_heuristic': 'TEMPERANCE',
                'guess_original_bind_pose': True
            }
            # Use default operator which usually preserves textures
            bpy.ops.import_scene.gltf(filepath=path)
        except Exception as e:
            print(f"GLTF import error: {e}, trying fallback...")
            bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
    
    after = set(bpy.context.scene.objects)
    new = list(after - before)
    
    # Enable nodes for materials to preserve textures
    for obj in new:
        if obj.type == 'MESH':
            for mat in obj.data.materials:
                if mat:
                    mat.use_nodes = True
    
    # Pick largest mesh
    meshes = [o for o in new if o.type=='MESH']
    root = None
    if meshes:
        meshes.sort(key=lambda o: (len(o.data.vertices), 
                                  o.dimensions.x*o.dimensions.y*o.dimensions.z), 
                   reverse=True)
        root = meshes[0]
    else:
        root = new[0] if new else None
    
    if root:
        root.name = name_hint
    
    # Check if materials have textures
    if root and root.type == 'MESH':
        print(f"Materials on {root.name}:")
        for i, mat in enumerate(root.data.materials):
            if mat:
                print(f"  Material {i}: {mat.name}")
                if mat.use_nodes:
                    has_texture = any(node.type == 'TEX_IMAGE' 
                                     for node in mat.node_tree.nodes)
                    print(f"    Has texture nodes: {has_texture}")
    
    return root


def setup_render_lights():
    """Setup area lights for orthographic rendering (XY plane view) - 3-light setup"""
    import time
    lights = []
    
    # Generate a unique timestamp for light names
    timestamp = str(int(time.time()))[-4:]
    
    # Camera is at (0, 0, dist) looking along -Z (towards XY plane)
    
    # 1) FRONT light - near camera position, strongest light (as SQUARE)
    bpy.ops.object.light_add(type='AREA', location=(0, 50, 75))
    front_light = bpy.context.active_object
    front_light.name = f"Render_Front_Light_{timestamp}"
    front_light.data.energy = 40000  # Strongest light
    front_light.data.shape = 'SQUARE'  # Changed to SQUARE
    front_light.data.size = 50  # Both dimensions will be 100 (square)
    front_light.rotation_euler = (-0.2, 0, 0)  # Tilted down toward scene
    lights.append(front_light)
    
    # 2) LEFT light - positioned to left side (as SQUARE)
    bpy.ops.object.light_add(type='AREA', location=(-100, 25, 60))
    left_light = bpy.context.active_object
    left_light.name = f"Render_Left_Light_{timestamp}"
    left_light.data.energy = 60000  # Medium strength
    left_light.data.shape = 'SQUARE'  # Changed to SQUARE
    left_light.data.size = 200  # Both dimensions will be 40 (square)
    left_light.rotation_euler = (-0.15, -1.0, 0)  # Facing toward scene center
    lights.append(left_light)
    
    # 3) RIGHT light - positioned to right side (as SQUARE)
    bpy.ops.object.light_add(type='AREA', location=(100, 25, 60))
    right_light = bpy.context.active_object
    right_light.name = f"Render_Right_Light_{timestamp}"
    right_light.data.energy = 60000  # Medium strength
    right_light.data.shape = 'SQUARE'  # Changed to SQUARE
    right_light.data.size = 200  # Both dimensions will be 40 (square)
    right_light.rotation_euler = (-0.15, 1.0, 0)  # Facing toward scene center
    lights.append(right_light)
    
    # 4) Top fill light for better overall illumination (as SQUARE)
    bpy.ops.object.light_add(type='AREA', location=(0, 0, 125))
    top_light = bpy.context.active_object
    top_light.name = f"Render_Top_Fill_{timestamp}"
    top_light.data.energy = 200000
    top_light.data.shape = 'SQUARE'  # Changed to SQUARE
    top_light.data.size = 250  # Both dimensions will be 50 (square)
    top_light.rotation_euler = (0, 0, 0)  # Pointing straight down
    lights.append(top_light)
    
    # Brighter ambient for better overall illumination
    world = bpy.context.scene.world
    if world:
        world.use_nodes = True
        bg = world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs['Color'].default_value = (0.15, 0.15, 0.15, 1.0)
            bg.inputs['Strength'].default_value = 0.2
    
    return lights

def create_card_corner_markers(card_obj, card_width, card_height, marker_size=8.0, marker_thickness=0.3):
    """
    Create L-shaped corner markers at the four corners of the card.
    Each marker is made of two thin rectangles forming an L shape that fits inside the card.
    
    Args:
        card_obj: The card object
        card_width: Total width of the card (mm)
        card_height: Total height of the card (mm)
        marker_size: Size of the L shape arms (mm)
        marker_thickness: Thickness of the L shape lines (mm)
    
    Returns:
        List of marker objects
    """
    import bpy
    import bmesh
    from mathutils import Vector
    
    markers = []
    
    # Card half dimensions
    half_w = card_width / 2.0
    half_h = card_height / 2.0
    
    # Corner configurations: (corner_x, corner_y, x_sign, y_sign, rotation)
    # x_sign: +1 for right side, -1 for left side
    # y_sign: +1 for top side, -1 for bottom side
    corners = [
        # Bottom-left: L shape goes right (horizontal) and up (vertical)
        (-half_w, -half_h, +1, +1, 0),
        # Bottom-right: L shape goes left (horizontal) and up (vertical)  
        ( half_w, -half_h, -1, +1, 90),
        # Top-right: L shape goes left (horizontal) and down (vertical)
        ( half_w,  half_h, -1, -1, 180),
        # Top-left: L shape goes right (horizontal) and down (vertical)
        (-half_w,  half_h, +1, -1, 270),
    ]
    
    corner_names = ["BottomLeft", "BottomRight", "TopRight", "TopLeft"]
    
    # Create an L shape at each corner
    for (corner_x, corner_y, x_sign, y_sign, rotation), name in zip(corners, corner_names):
        bm = bmesh.new()
        
        # Create horizontal rectangle (along X axis)
        # Vertices for horizontal rectangle
        h_verts = [
            Vector((0, -marker_thickness/2, 0)),
            Vector((x_sign * marker_size, -marker_thickness/2, 0)),
            Vector((x_sign * marker_size,  marker_thickness/2, 0)),
            Vector((0,  marker_thickness/2, 0)),
        ]
        
        # Create vertical rectangle (along Y axis)
        # Vertices for vertical rectangle
        v_verts = [
            Vector((-marker_thickness/2, 0, 0)),
            Vector(( marker_thickness/2, 0, 0)),
            Vector(( marker_thickness/2, y_sign * marker_size, 0)),
            Vector((-marker_thickness/2, y_sign * marker_size, 0)),
        ]
        
        # Create faces for both rectangles
        h_face = bm.faces.new([bm.verts.new(v) for v in h_verts])
        v_face = bm.faces.new([bm.verts.new(v) for v in v_verts])
        
        # Merge overlapping vertices at the corner (0,0)
        # Find vertices at (0,0) and merge them
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.001)
        
        # Extrude the L shape upward slightly
        extruded = bmesh.ops.extrude_face_region(bm, geom=[h_face, v_face])
        extruded_verts = [ele for ele in extruded['geom'] if isinstance(ele, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=extruded_verts, vec=Vector((0, 0, marker_thickness)))
        
        # Create mesh and object
        me = bpy.data.meshes.new(f"CornerMarker_{name}")
        bm.to_mesh(me)
        bm.free()
        
        marker = bpy.data.objects.new(f"CornerMarker_{name}", me)
        
        # Position at card corner
        marker.location = Vector((corner_x, corner_y, 0.1))  # Slightly above card
        
        # Add a bright red emission material so markers are clearly visible
        mat = bpy.data.materials.new(f"MarkerMaterial_{name}")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (1.0, 0.0, 0.0, 1.0)  # Bright red
        em.inputs["Strength"].default_value = 10.0  # Very bright
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        
        marker.data.materials.append(mat)
        
        # Link to scene
        bpy.context.scene.collection.objects.link(marker)
        markers.append(marker)
    
    return markers

def render_scene_ortho(output_path, res_x=1920, res_y=1080):
    """Render the entire scene with orthographic projection (XY plane view)"""
    import bpy
    from mathutils import Vector, Matrix
    
    bpy.context.view_layer.update()
    
    # 1) Collect all objects we want to render:
    # - All MESH objects (models, figures, accessories)
    # - All FONT/CURVE objects (text group)
    # - Corner markers (we'll create these)
    # But NOT the card itself
    all_objs = list(bpy.data.objects)
    
    # Find the card object (look for "Card" or similar)
    card_obj = None
    for o in all_objs:
        if "card" in o.name.lower() and o.type == 'MESH':
            card_obj = o
            break
    
    # Create corner markers if we have a card
    marker_objs = []
    if card_obj:
        try:
            # Get card dimensions from the card object bounds
            mn, mx = world_aabb(card_obj)
            card_width = mx.x - mn.x
            card_height = mx.y - mn.y
            
            print(f"Card dimensions from bounds: {card_width:.2f} x {card_height:.2f} mm")
            
            # Create corner markers
            marker_objs = create_card_corner_markers(
                card_obj, 
                card_width, 
                card_height,
                marker_size=2.0,  # 8mm crosshair arms
                marker_thickness=0.1  # 0.3mm thick lines
            )
            print(f"Created {len(marker_objs)} corner markers for card")
        except Exception as e:
            print(f"Failed to create corner markers: {e}")
    
    # Objects to render: everything except the card, but INCLUDING markers
    render_objs = []
    for o in all_objs:
        # Include objects by type
        if o.type in {'MESH', 'FONT', 'CURVE'}:
            # Skip the card if found
            if card_obj and o == card_obj:
                continue
            render_objs.append(o)
    
    # Add markers to render objects
    render_objs.extend(marker_objs)
    
    if not render_objs:
        print("[WARN] No objects to render; skipping.")
        return
    
    # 2) Hide everything else temporarily
    prev_hide = {o: o.hide_render for o in all_objs}
    for o in all_objs:
        o.hide_render = True
    for o in render_objs:
        o.hide_render = False
    
    bpy.context.view_layer.update()
    
    # 3) Union AABB of all renderable objects in WORLD space (including markers)
    mn = Vector((+1e30, +1e30, +1e30))
    mx = Vector((-1e30, -1e30, -1e30))
    for obj in render_objs:
        a, b = world_aabb(obj)
        mn.x = min(mn.x, a.x); mn.y = min(mn.y, a.y); mn.z = min(mn.z, a.z)
        mx.x = max(mx.x, b.x); mx.y = max(mx.y, b.y); mx.z = max(mx.z, b.z)
    
    center = (mn + mx) * 0.5
    w = (mx.x - mn.x)
    h = (mx.y - mn.y)
    
    if w <= 1e-9 or h <= 1e-9:
        print("[WARN] Zero XY bounds; skipping render.")
        for o, hflag in prev_hide.items(): 
            o.hide_render = hflag
        return
    
    print(f"[DEBUG] Render objects: {[o.name for o in render_objs]}")
    print(f"[DEBUG] Bounds: w={w:.2f}, h={h:.2f}, center={center}")
    
    # 4) Setup orthographic camera for XY plane view
    cam = bpy.data.objects.get("_TMP_SceneCam")
    if not cam:
        cam_data = bpy.data.cameras.new("_TMP_SceneCam")
        cam = bpy.data.objects.new("_TMP_SceneCam", cam_data)
        bpy.context.scene.collection.objects.link(cam)
    
    cam.data.type = 'ORTHO'
    
    # Camera looking along -Z axis (top view of XY plane)
    # Right = +X, Up = +Y, Forward = -Z
    right = Vector((1, 0, 0))
    up    = Vector((0, 1, 0))
    dist  = 50.0  # Distance from scene (orthographic ignores this for projection)
    
    # Position camera so it looks at the scene from above
    # Center in XY, positioned above the scene in Z
    cam.matrix_world = Matrix((
        ( right.x, up.x,  0.0, center.x              ),
        ( right.y, up.y,  0.0, center.y              ),
        ( right.z, up.z,  1.0, center.z + dist       ),
        (   0.0,    0.0,  0.0, 1.0                   ),
    ))
    
    # Add margin (10% around the objects)
    margin = 0.1
    w *= (1.0 + margin * 2.0)
    h *= (1.0 + margin * 2.0)
    cam.data.ortho_scale = max(w, h)
    
    # 5) Setup lighting for the scene - KEEP LIGHTS IN SCENE FOR DEBUGGING
    lights = setup_render_lights()
    
    # 6) Configure render settings - KEEP CYCLES
    sc = bpy.context.scene
    sc.camera = cam
    
    # Keep CYCLES as the renderer
    sc.render.engine = 'CYCLES'
    
    # Configure CYCLES settings for faster rendering
    sc.cycles.samples = 64  # Reduced for speed
    sc.cycles.use_denoising = True
    
    # Enable GPU if available
    sc.cycles.device = 'GPU'
    try:
        prefs = bpy.context.preferences
        cprefs = prefs.addons['cycles'].preferences
        cprefs.get_devices()
        for device in cprefs.devices:
            if device.type in ['CUDA', 'OPTIX', 'HIP']:
                device.use = True
    except:
        sc.cycles.device = 'CPU'
    
    # Set resolution - use fixed resolution from args
    sc.render.resolution_x = res_x
    sc.render.resolution_y = res_y
    
    # Calculate aspect ratio and adjust ortho scale if needed
    scene_aspect = w / h if h > 0 else 1.0
    render_aspect = res_x / res_y if res_y > 0 else 1.0
    
    # Adjust ortho scale to fit the render aspect ratio
    if scene_aspect > render_aspect:
        # Scene is wider than render area, scale based on width
        cam.data.ortho_scale = w * (1.0 + margin * 2.0)
    else:
        # Scene is taller than render area, scale based on height
        # Adjust width to match aspect ratio
        needed_width = h * render_aspect
        cam.data.ortho_scale = max(needed_width, h) * (1.0 + margin * 2.0)
    
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.render.film_transparent = True
    
    # Ensure output directory exists
    abs_path = bpy.path.abspath(output_path)
    abs_path = os.path.abspath(abs_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    sc.render.filepath = abs_path
    
    # 7) Render
    print(f"Rendering scene to: {output_path}")
    print(f"  Camera ortho scale: {cam.data.ortho_scale:.2f}")
    print(f"  Resolution: {sc.render.resolution_x}x{sc.render.resolution_y}")
    print(f"  Objects rendered: {len(render_objs)}")
    print(f"  Lights created: {[light.name for light in lights]}")
    
    bpy.ops.render.render(write_still=True)
    
    # 8) Cleanup - BUT DON'T DELETE LIGHTS OR MARKERS
    # Remove temporary camera only
    if "_TMP_SceneCam" in bpy.data.objects:
        bpy.data.objects.remove(cam, do_unlink=True)
    
    # DO NOT remove lights or markers - keep them in scene for debugging
    # They will be saved with the .blend file
    
    # Restore visibility
    for o, hflag in prev_hide.items():
        o.hide_render = hflag
    
    print(f"Scene render complete: {output_path}")
    print(f"Lights kept in scene for debugging: {[light.name for light in lights]}")
    print(f"Corner markers kept in scene: {len(marker_objs)}")

def main():
    args = parse_args()
    ensure_outdir(args.outdir)
    ensure_middir(args.middir)

    clear_scene()
    set_units_mm()


    # Make card (top at Z=0, bottom at -card_thickness)
    # card = create_rounded_card(args.card_width, args.card_height, args.card_thickness, args.fillet)
    # Make card (top at Z=0, bottom at -card_thickness)
    card = create_beveled_card(args.card_width, args.card_height, args.card_thickness, args.fillet)
    if args.has_hole:
        cut_key_hole(card_obj=card, card_w=args.card_width, card_h=args.card_height, card_th=args.card_thickness, hole_d=args.hole_d, hole_margin=args.hole_margin, corner=args.hole_corner)

    args.card_width -= args.padding_card * 2
    args.card_height -= args.padding_card * 2
    
    # --- 1) build the two texts ---
    title_obj = make_text(args.title,    size=args.TS,        extrude=args.text_extr, font_path=args.font, roll_deg=-90)
    sub_obj   = make_text(args.subtitle, size=args.TS * 0.6,  extrude=args.text_extr, font_path=args.font, roll_deg=-90)
    # stack them (subtitle below title) with margin MT
    place_sub_below_title(title_obj, sub_obj, margin_MT=float(args.MT))

    # --- 2) group them under an Empty, so we can scale/position as one ---
    text_group = group_under_empty([title_obj, sub_obj], name="TextGroup")

    # --- 3) fit group into the top slot (height = card_height/5), and make total text height = TH ---
    slot_top_y    = +args.card_height/2.0
    slot_bottom_y = slot_top_y - (args.card_height/5.0)

    scale_group_y_to_height(
        text_group,
        children=[title_obj, sub_obj],
        target_height=float(args.TH),                # total group height you want
        slot_bottom_y=slot_bottom_y,
        slot_top_y=slot_top_y,
    )

    # center horizontally (X=0) and sit on card top with a tiny lift
    # (group_under_empty already centered X via union; ensure x=0 if your card is centered)
    text_group.location.x = 0.0
    lift_group_to_card_top(text_group, [title_obj, sub_obj], card_obj=card, lift=float(args.text_lift))


    # Compute bands/regions (XY, top view)
    H_upper = args.card_height * args.upper_ratio               # upper band height
    H_lower = args.card_height - H_upper                        # lower band height
    # Lower-left (figure) width 3/5W, lower-right (accessories) width 2/5W
    W_left  = args.card_width * (3.0/5.0)
    W_right = args.card_width - W_left                         # 2/5W

    # Regions defined with centers to simplify placement
    # Coordinate frame: origin at card center, +Y up, +X right. Card top lies on Z=0.
    # LOWER band spans from y = -args.card_height/2  ..  y = -args.card_height/2 + H_lower
    lower_y_min = -args.card_height/2.0
    lower_y_max = lower_y_min + H_lower
    lower_y_center = 0.5*(lower_y_min + lower_y_max)

    # Upper band center (for text, if you later want it)
    upper_y_min = lower_y_max
    upper_y_max = args.card_height/2.0
    upper_y_center = 0.5*(upper_y_min + upper_y_max)

    # Left figure slot (in lower band): width = W_left, height = H_lower
    fig_slot_w = W_left
    fig_slot_h = H_lower

    # Right accessories column: width = W_right, height = (2/3) * card_height  (as specified)
    acc_slot_w = W_right
    acc_slot_h = (2.0/3.0) * args.card_height
    acc_y_center = lower_y_center  # center the 2/3H column within lower band

    # Accessory vertical partitioning into 3 equal parts
    acc_cell_h = acc_slot_h / 3.0

    # X centers
    left_x_min = -args.card_width/2.0
    left_x_center = left_x_min + fig_slot_w/2.0
    right_x_max = args.card_width/2.0
    right_x_center = right_x_max - acc_slot_w/2.0

    # Create empties for slots (handy for debugging in UI)
    # (Comment these three lines out if you don’t need helpers)
    # bpy.ops.object.empty_add(type='PLAIN_AXES', location=(left_x_center, lower_y_center, 0)); bpy.context.active_object.name="FIGURE_SLOT"
    # bpy.ops.object.empty_add(type='PLAIN_AXES', location=(right_x_center, acc_y_center + acc_cell_h*+1, 0)); bpy.context.active_object.name="ACC1_SLOT"
    # bpy.ops.object.empty_add(type='PLAIN_AXES', location=(right_x_center, acc_y_center + acc_cell_h* 0, 0)); bpy.context.active_object.name="ACC2_SLOT"


    # ----------------- import + orient + fit + place -----------------
    # Figure
    fig = import_model_with_textures(args.figure, "Figure")
    slot_depth = 10000
    if fig:        
        needs_roll = needs_x_roll(fig)
        apply_xforms(fig)
        if needs_roll:
            roll_about_parallel_world_x(fig, -90)
        
        # orient_object(fig, head_bias=True)          # main character
        center_xy(fig);             # center before fitting
        rest_on_z0(fig)             # put on the card top plane (Z=0)
        slot_depth = uniform_fit(fig, fig_slot_w, fig_slot_h, margin=args.margin_figure)
        # place: center of left lower region
        fig.location.x = left_x_center
        fig.location.y = lower_y_center
        snap_bottom_to_base_top(fig, card)          # just touching the card
        sink_into_card(fig, card, max_fraction=1.0/3.0)
        bpy.context.view_layer.update()

    # Accessories
    acc_objs = []
    acc_count = min(3, len(args.acc))
    # Y centers for 3 vertical parts: top/mid/bottom within acc column centered at acc_y_center
    start_y = acc_y_center + (acc_slot_h/2.0) - acc_cell_h/2.0
    centers_y = [ start_y - i*acc_cell_h for i in range(acc_count) ]

    for i in range(acc_count):
        path = args.acc[i]
        if not os.path.exists(path): continue
        acc = import_model_with_textures(path, f"Accessory_{i+1}")
        if not acc: continue
        apply_xforms(acc)
        if needs_roll:
            roll_about_parallel_world_x(acc, -90)
            
        center_xy(acc); rest_on_z0(acc)
        # fit inside a square cell of height acc_cell_h and width acc_slot_w
        uniform_fit(acc, acc_slot_w, acc_cell_h, margin=args.margin_accessories, target_d=slot_depth)
        # place
        acc.location.x = right_x_center
        acc.location.y = centers_y[i]
        snap_bottom_to_base_top(acc, card)          # just touching the card
        sink_into_card(acc, card, max_fraction=1.0/3.0)
        bpy.context.view_layer.update()
        acc_objs.append(acc)

    # ----------------- placement export (top-view XY) -----------------
    recs = []

    # Card (use world dims; your card is centered at origin with top on Z=0)
    c_minx, c_miny, c_maxx, c_maxy = obj_xy_aabb(card)
    recs.append(pack_xy_record(
        "Card", c_minx, c_miny, c_maxx, c_maxy,
        rot_z_rad=card.matrix_world.to_euler('XYZ').z
    ))

    # Figure
    if fig:
        f_minx, f_miny, f_maxx, f_maxy = obj_xy_aabb(fig)
        recs.append(pack_xy_record(
            "base_character", f_minx, f_miny, f_maxx, f_maxy,
            rot_z_rad=fig.matrix_world.to_euler('XYZ').z
        ))

    # Accessories
    for i, acc in enumerate(acc_objs, start=1):
        a_minx, a_miny, a_maxx, a_maxy = obj_xy_aabb(acc)
        recs.append(pack_xy_record(
            f"accessory_{i}", a_minx, a_miny, a_maxx, a_maxy,
            rot_z_rad=acc.matrix_world.to_euler('XYZ').z
        ))

    # Text group (union of title + subtitle)
    tg_minx, tg_miny, tg_maxx, tg_maxy = group_xy_aabb([title_obj, sub_obj])
    recs.append(pack_xy_record(
        "TextGroup", tg_minx, tg_miny, tg_maxx, tg_maxy,
        rot_z_rad=text_group.matrix_world.to_euler('XYZ').z
    ))

    # Meta (use post-padding W/H so they match actual layout space)
    meta = {
        "job_id": args.job_id,
        "units": "mm",
        "card": {
            "W": float(args.card_width),
            "H": float(args.card_height),
            "card_thickness": float(args.card_thickness),
            "upper_ratio": float(args.upper_ratio),
            "padding_card": float(args.padding_card),
        },
        "slots": {
            "figure": {"w": float(fig_slot_w), "h": float(fig_slot_h)},
            "accessories": {"w": float(acc_slot_w), "h": float(acc_slot_h)},
            "text_strip": {"h": float(args.card_height/5.0)}
        }
    }

    # File path (default or user-specified)
    layout_path = os.path.join(args.middir, args.model_name_seed + f"_layout.json")
    write_layout_json(layout_path, meta, recs)

    # ----------------- export -----------------
    ensure_outdir(args.outdir)
    ensure_middir(args.middir)
    
    print(f"Rendering scene with texture")    
    render_path = os.path.join(args.middir, args.model_name_seed + f"_scene_render.png")
    render_scene_ortho(
        output_path=render_path,
        res_x=args.render_resx,
        res_y=args.render_resy
    )

#def someMore():
    group_png = os.path.join(args.middir, f"TextGroup.png")

    # diagnose_text_group_front(text_group, px=1600, margin=0.08)
    # render_text_group_front_png(text_group, group_png, px=1600, margin=0.08, color=(1,0,0,1))



    blend_path = os.path.join(args.outdir, args.model_name_seed + f"_model.blend")
    stl_path = os.path.join(args.outdir, args.model_name_seed + f"_model.stl")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[OK] Blend: {blend_path}")
    
    # Save combined STL of all meshes (card + models)
    export_scene_as_stl(stl_path)
    print(f"[OK] STL: {stl_path}")



    print("[DONE]")


if __name__ == "__main__":
    main()