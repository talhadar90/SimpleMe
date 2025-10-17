REM System Python runs the processor, which will spawn Blender headless
python "blender_processor.py" ^
  --blender "blender.exe" ^
  --figure  "3d\base_character_3d.glb" ^
  --acc     "3d\accessory_1_3d.glb" "3d\accessory_2_3d.glb" "3d\accessory_3_3d.glb" ^
  --outdir  "blender_processor_out" ^
  --jobid  "orig_001"
