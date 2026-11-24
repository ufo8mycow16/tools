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

REPAIR_TIMEOUT = 90   # seconds
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


def _matrix(tf):
    """3MF transform "m00 m01 m02 m10 ... m32" -> 4x4 (row vectors)."""
    M = np.eye(4)
    if tf:
        M[:, :3] = np.array([float(x) for x in tf.split()]).reshape(4, 3)
    return M


def mesh_from_3mf(data):
    """All meshes in the package, joined, with build-item and component transforms applied.
    Windows' repair can hand back an object made of components (references to other
    objects, possibly in other .model files) instead of one plain mesh - handled here."""
    roots = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".model")]
        for n in names:
            r = ET.fromstring(z.read(n))
            for el in r.iter():                  # drop namespaces
                if "}" in el.tag:
                    el.tag = el.tag.split("}", 1)[1]
                for k in list(el.attrib):
                    if "}" in k:
                        el.attrib[k.split("}", 1)[1]] = el.attrib.pop(k)
            roots.append(r)
    if not roots:
        return None
    objects = {}                                  # id -> ("mesh", V, F) or ("comp", [(id, M)])
    for r in roots:
        for obj in r.iter("object"):
            oid = obj.get("id")
            mesh = obj.find("mesh")
            if mesh is not None and mesh.find("vertices") is not None and mesh.find("triangles") is not None:
                V = np.array([[float(v.get("x")), float(v.get("y")), float(v.get("z"))]
                              for v in mesh.find("vertices")], dtype=float).reshape(-1, 3)
                F = np.array([[int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))]
                              for t in mesh.find("triangles")], dtype=np.int64).reshape(-1, 3)
                if oid not in objects or objects[oid][0] != "mesh":
                    objects[oid] = ("mesh", V, F)
                continue
            comps = obj.find("components")
            if comps is not None and oid not in objects:
                objects[oid] = ("comp", [(c.get("objectid"), _matrix(c.get("transform"))) for c in comps])
    build = next((r.find("build") for r in roots if r.find("build") is not None), None)
    use = [(it.get("objectid"), _matrix(it.get("transform"))) for it in (build if build is not None else [])]
    use = use or [(k, np.eye(4)) for k, v in objects.items() if v[0] == "mesh"]
    parts_V, parts_F, off = [], [], 0

    def add(oid, M, depth=0):
        nonlocal off
        o = objects.get(oid)
        if o is None or depth > 8:
            return
        if o[0] == "mesh":
            V = np.c_[o[1], np.ones(len(o[1]))] @ M
            parts_V.append(V[:, :3])
            parts_F.append(o[2] + off)
            off += len(o[1])
        else:
            for cid, CM in o[1]:
                add(cid, CM @ M, depth + 1)

    for oid, M in use:
        add(oid, M)
    if not parts_V or not sum(len(f) for f in parts_F):
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
        # never let a stuck repair hang BrickForge - give up after a minute and a half
        data = asyncio.run(asyncio.wait_for(_repair_async(mesh_to_3mf(V, F)), timeout=REPAIR_TIMEOUT))
        r = mesh_from_3mf(data)
        if r is None:
            _err = f"Windows sent back a file with no shape BrickForge could read ({len(data):,} bytes)"
        return r
    except asyncio.TimeoutError:
        _err = "Windows took too long to repair it"
        return None
    except Exception as e:      # noqa
        _err = e
        return None


def last_error():
    return str(_err) if _err else ""
