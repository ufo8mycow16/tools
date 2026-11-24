"""Normal map (tangent space, glTF/OpenGL green-up) -> height map for real carved relief.
python3 normal2height.py normal.png height.npy [preview.png] [highpass_px=25]
FFT (Frankot-Chellappa) integration in UV space, high-passed so only local relief is kept,
scaled to -1..1. Mirrored UV islands are fine (height is the same either side).
If a part comes out as grooves instead of ridges, flip the sign of q."""
import sys, numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
a = sys.argv[1:]; hp = float(a[3]) if len(a) > 3 else 25
N = np.asarray(Image.open(a[0]).convert('RGB'), float) / 255 * 2 - 1
nz = np.clip(N[:, :, 2], 0.2, 1); p = -N[:, :, 0] / nz; q = N[:, :, 1] / nz
H, W = p.shape; fx = np.fft.fftfreq(W) * 2 * np.pi; fy = np.fft.fftfreq(H) * 2 * np.pi
FX, FY = np.meshgrid(fx, fy); den = FX ** 2 + FY ** 2; den[0, 0] = 1
Z = (-1j * FX * np.fft.fft2(p) - 1j * FY * np.fft.fft2(q)) / den; Z[0, 0] = 0
h = np.real(np.fft.ifft2(Z)); h -= gaussian_filter(h, hp)
flat = (np.abs(N[:, :, 0]) < 0.02) & (np.abs(N[:, :, 1]) < 0.02)
h = np.clip(h / np.percentile(np.abs(h[~flat]), 99.5), -1, 1)
np.save(a[1], h.astype(np.float32))
if len(a) > 2: Image.fromarray(((h * 0.5 + 0.5) * 255).astype(np.uint8)).save(a[2])
