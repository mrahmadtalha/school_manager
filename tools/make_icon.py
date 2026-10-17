from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "logo.png"
OUT = ROOT / "installer" / "assets" / "SchoolManager.ico"

src = Image.open(SRC).convert("RGBA")
side = max(src.size)

# Make it square without stretching (transparent padding)
canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
canvas.paste(src, ((side - src.width) // 2, (side - src.height) // 2), src)
if side < 256:
    canvas = canvas.resize((256, 256), Image.LANCZOS)

canvas.save(OUT, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Saved", OUT)