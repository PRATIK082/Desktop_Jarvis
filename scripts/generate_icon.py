"""Generate a minimal valid 16x16 32bpp placeholder icon for Tauri Windows build."""
import struct
from pathlib import Path

W = H = 16
pixel = bytes([0x00, 0xFF, 0xC8, 0xFF])  # BGRA: cyan with full alpha
pixel_data = pixel * (W * H)

# BITMAPINFOHEADER (40 bytes)
dib = struct.pack(
    "<iiiHHIIiiII",
    40, W, H, 1, 32, 0, W * H * 4, 0, 0, 0, 0,  # biSize, biWidth, biHeight, biPlanes, biBitCount, biCompression, biSizeImage, XPels, YPels, ClrUsed, ClrImportant
)
image_data = dib + pixel_data
image_size = len(image_data)
image_offset = 6 + 16  # ICONDIR + one ICONDIRENTRY

# ICONDIR: reserved=0, type=1, count=1
icon_dir = struct.pack("<HHH", 0, 1, 1)
# ICONDIRENTRY: width, height, colorCount, reserved, planes, bitCount, sizeInBytes, offset
icon_entry = struct.pack("<BBBBhhII", W, H, 0, 0, 1, 32, image_size, image_offset)

ico = icon_dir + icon_entry + image_data

out = Path("apps/desktop/src-tauri/icons/icon.ico")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(ico)
print(f"Wrote {out} ({len(ico)} bytes)")
