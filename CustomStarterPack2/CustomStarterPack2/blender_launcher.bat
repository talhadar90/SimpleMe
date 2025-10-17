"blender.exe" ^
  --background --python "starter_pack_layout.py" -- ^
  --figure "3d\base_character_3d.glb" ^
  --accessories "3d\accessory_1_3d.glb" "3d\accessory_2_3d.glb" "3d\accessory_3_3d.glb" ^
  --outdir "blender_out" --job_id "job_001" ^
  --base_w 130 --base_h 190 --base_th 5 --text_h 50 ^
  --figure_w 70 --figure_h 140 --gap 10 --acc_size 30 --acc_count 4
