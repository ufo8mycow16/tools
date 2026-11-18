"""M2 (+skin, textures) -> npz + PNGs for the Blender builder."""
import sys, os, json, numpy as np
sys.path.insert(0, '/home/claude/wowx'); import plan, m2, blp
from PIL import Image
def dump(m2fid, out, item_tex=None, skin_fid=None):
    os.makedirs(out, exist_ok=True)
    m = m2.M2(plan.read_fid(m2fid)); s = m2.Skin(plan.read_fid(skin_fid or m.skin_fids[0])); v = m.verts()
    texs = m.textures(); tl = m.u16list('texture_lookup')
    faces = []; mats = []; texfiles = {}
    for bi, b in enumerate(s.batches):
        if b['layer'] != 0: continue
        f = s.faces(b['sub']); faces.append(f)
        t = texs[tl[b['tcombo']]]
        fid = t['fid'] or (item_tex if t['type'] == 2 else 0)
        if fid and fid not in texfiles:
            blp.decode(plan.read_fid(fid), keep_alpha=False).convert('RGB').save(f'{out}/{fid}.png'); texfiles[fid] = f'{fid}.png'
        mats += [fid] * len(f)
    np.savez(f'{out}/mesh.npz', pos=v['pos'], nrm=v['nrm'], uv=v['uv'], faces=np.concatenate(faces), mat=np.array(mats))
    json.dump(dict(name=m.name, textures=texfiles), open(f'{out}/info.json', 'w'))
    return m
if __name__ == '__main__':
    a = sys.argv[1:]; dump(int(a[0]), a[1], int(a[2]) if len(a) > 2 and a[2] != '0' else None)
