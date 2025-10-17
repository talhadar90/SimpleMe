# run_starter_pack.py
import sys, os, json, argparse, importlib.util

def load_module(py_path, mod_name="starter_pack_layout"):
    spec = importlib.util.spec_from_file_location(mod_name, py_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main():
    p = argparse.ArgumentParser()
    # path to your existing blender layout script (the one that does placement)
    p.add_argument("--script", required=True)          # e.g., D:\blender\starter_pack_layout.py
    p.add_argument("--config", required=True)          # JSON with inputs (below)
    args = p.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    mod = load_module(args.script)

    # Inject inputs as globals for maximum compatibility with your current script
    # (works even if your script expects these names as globals)
    if "figure" in cfg:        setattr(mod, "FIGURE", cfg["figure"])
    if "accessories" in cfg:   setattr(mod, "ACCESSORIES", cfg["accessories"])
    if "output_dir" in cfg:    setattr(mod, "OUTPUT_DIR", cfg["output_dir"])
    if "job_id" in cfg:        setattr(mod, "JOB_ID", cfg.get("job_id", "run"))

    # If your script exposes a main(figure, accessories, output_dir, job_id) use it:
    if hasattr(mod, "main"):
        mod.main(
            figure=cfg.get("figure", ""),
            accessories=cfg.get("accessories", []),
            output_dir=cfg.get("output_dir", "."),
            job_id=cfg.get("job_id", "run"),
        )
    else:
        # Otherwise, importing ran everything; nothing else to do.
        pass

if __name__ == "__main__":
    main()
