from ..base_module import BaseModule
from ..context import Context

class MetaDemo(BaseModule):
    """Pretend to extract metadata."""

    def run(self, ctx: Context) -> None:
        files = ctx.pull("scan.files", [])
        fake_meta = {str(f): {"duration": 0, "codec": "demo"} for f in files}
        ctx.push("meta.info", fake_meta)
        print(f"MetaDemo processed: {fake_meta}") 