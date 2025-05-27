from pathlib import Path
from tqdm import tqdm
from ..base_module import BaseModule
from ..context import Context

class ScanDemo(BaseModule):
    """Dummy scan – collects *.mp4 files."""

    def run(self, ctx: Context) -> None:
        root = Path(ctx.cfg.root)
        # Create dummy files for the demo if the root directory is empty or does not exist
        if not root.exists() or not any(root.iterdir()):
            root.mkdir(parents=True, exist_ok=True)
            for i in range(5):
                with open(root / f"video{i}.mp4", "w") as f:
                    f.write("dummy mp4 content")
            print(f"Created dummy .mp4 files in {root}")

        files = [p for p in root.rglob("*.mp4")]
        for _ in tqdm(files, desc="Scanning"):
            pass  # demo: no work
        ctx.push("scan.files", files)
        print(f"ScanDemo found: {files}") 