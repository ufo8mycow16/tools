"""Mesh repair using the 3D-printing repair service built into Windows 10/11
(Windows.Graphics.Printing3D) - the same service Bambu Studio's "Fix model" uses.

Flow: write the mesh as a small 3MF in memory -> Printing3D3MFPackage loads it ->
Printing3DModel.RepairAsync() -> save back to 3MF -> read the repaired mesh.
Needs the pywinrt packages (installed by build.bat). Everything fails soft:
if anything is missing or goes wrong, repair() returns None.
"""
import io, sys, zipfile
import xml.etree.ElementTree as ET
import numpy as np

_err = None
try:
    if sys.platform != "win32":
        raise ImportError("not Windows")
    import asyncio
    from winrt.windows.graphics.printing3d import Printing3D3MFPackage
    from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter, DataReader
    AVAILABLE = True
except Exception as e:          # noqa
    AVAILABLE = False
    _err = e

NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


def why_unavailable():
    return str(_err) if _err else ""


# ---------------------------------------------------------------- 3MF in/out
def mesh_to_3mf(V, F):
    vx = "".join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in V)
    tr = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in F)
    model = (f'<?xml version="1.0" encoding="UTF-8"?>'
             f'<model unit="millimeter" xml:lang="en-US" xmlns="{NS}">'
             f'<resources><object id="1" type="model"><mesh><vertices>{vx}</vertices>'
             f'<triangles>{tr}</triangles></mesh></object></resources>'
             f'<build><item objectid="1"/></build></model>')
    ctypes = ('<?xml version="1.0" encoding="UTF-8"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
              '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)
    return buf.getvalue()


def mesh_from_3mf(data):
    """All meshes in the package, joined (with each build item's transform applied)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name = next((n for n in z.namelist() if n.lower().endswith(".model")), None)
        root = ET.fromstring(z.read(name))
    for el in root.iter():                       # drop namespaces
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    objects = {}
    for obj in root.iter("object"):
        mesh = obj.find("mesh")
        if mesh is None:
            continue
        V = np.array([[float(v.get("x")), float(v.get("y")), float(v.get("z"))]
                      for v in mesh.find("vertices")], dtype=float).reshape(-1, 3)
        F = np.array([[int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))]
                      for t in mesh.find("triangles")], dtype=np.int64).reshape(-1, 3)
        objects[obj.get("id")] = (V, F)
    build = root.find("build")
    use = [(it.get("objectid"), it.get("transform")) for it in (build if build is not None else [])]
    use = use or [(k, None) for k in objects]
    parts_V, parts_F, off = [], [], 0
    for oid, tf in use:
        if oid not in objects:
            continue
        V, F = objects[oid]
        if tf:
            M = np.array([float(x) for x in tf.split()]).reshape(4, 3)
            V = V @ M[:3] + M[3]
        parts_V.append(V)
        parts_F.append(F + off)
        off += len(V)
    if not parts_V:
        return None
    return np.vstack(parts_V), np.vstack(parts_F)


# ---------------------------------------------------------------- Windows calls
async def _stream_from_bytes(data):
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(data)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)
    return stream


async def _bytes_from_stream(stream):
    size = stream.size
    reader = DataReader(stream.get_input_stream_at(0))
    await reader.load_async(size)
    buf = bytearray(size)
    try:
        reader.read_bytes(buf)
        return bytes(buf)
    except TypeError:
        b = reader.read_buffer(size)
        return bytes(memoryview(b))


async def _repair_async(data):
    pkg = Printing3D3MFPackage()
    stream = await _stream_from_bytes(data)
    model = await pkg.load_model_from_package_async(stream)
    await model.repair_async()
    await pkg.save_model_to_package_async(model)
    out = await pkg.save_async()
    return await _bytes_from_stream(out)


def repair(V, F):
    """Repaired (V, F), or None if the Windows repair isn't available or fails."""
    global _err
    if not AVAILABLE:
        return None
    try:
        data = asyncio.run(_repair_async(mesh_to_3mf(V, F)))
        return mesh_from_3mf(data)
    except Exception as e:      # noqa
        _err = e
        return None
