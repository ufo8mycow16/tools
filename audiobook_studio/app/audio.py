"""ffmpeg jobs: saving segments, building chapter audio, and exporting audiobooks (.m4b with chapters + cover,
or tagged MP3s)."""
from pathlib import Path
import json
import re
import shutil
import subprocess
import tempfile
import zipfile

from . import config

FF = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']


def check_ffmpeg():
    return shutil.which('ffmpeg') is not None


def save_segment(path, samples, sr):
    """float32 mono -> FLAC (lossless, about half the size of WAV). Returns duration in seconds."""
    import numpy as np
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()
    tmp = path.with_suffix('.partial.flac')
    subprocess.run(FF + ['-f', 's16le', '-ar', str(int(sr)), '-ac', '1', '-i', 'pipe:0', '-c:a', 'flac',
                         str(tmp)], input=pcm, check=True)
    tmp.replace(path)
    return len(samples) / float(sr)


def duration(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(path)],
                       capture_output=True, text=True)
    try:
        return float(json.loads(r.stdout)['format']['duration'])
    except Exception:
        return 0.0


def silence(ms, sr=24000):
    ms = max(0, int(ms))
    p = config.cache_dir() / 'silence' / f'{ms}_{sr}.flac'
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(FF + ['-f', 'lavfi', '-i', f'anullsrc=r={sr}:cl=mono', '-t', f'{ms / 1000:.3f}',
                             '-c:a', 'flac', str(p)], check=True)
    return p


def _concat_list(files, list_path):
    with open(list_path, 'w', encoding='utf-8') as f:
        for p in files:
            f.write("file '" + str(Path(p).resolve()).replace("'", "'\\''") + "'\n")


def build_chapter(parts, out_path, sr=24000):
    """parts: [(audio_path or None, gap_ms_after)] -> chapter .m4a. Returns the start time of every part."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    files, starts, t = [], [], 0.0
    lead = int(config.get('gap_chapter_start'))
    if lead:
        files.append(silence(lead, sr))
        t += lead / 1000
    for path, dur, gap in parts:
        starts.append(t)
        if path:
            files.append(path)
            t += dur
        if gap:
            files.append(silence(gap, sr))
            t += gap / 1000
    tail = int(config.get('gap_chapter_end'))
    if tail:
        files.append(silence(tail, sr))
        t += tail / 1000
    with tempfile.TemporaryDirectory() as td:
        lst = Path(td) / 'list.txt'
        _concat_list(files, lst)
        tmp = out_path.with_suffix('.partial.m4a')
        subprocess.run(FF + ['-f', 'concat', '-safe', '0', '-i', str(lst), '-c:a', 'aac', '-b:a',
                             config.get('chapter_bitrate'), '-ar', str(sr), '-ac', '1', '-movflags', '+faststart',
                             str(tmp)], check=True)
        tmp.replace(out_path)
    return starts, t


def _meta_escape(s):
    return re.sub(r'([=;#\\\n])', r'\\\1', s or '')


def safe_name(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '', s or '').strip().rstrip('.')
    return s[:120] or 'Audiobook'


def export_m4b(book, chapters, cover, out_path):
    """chapters: [{'title', 'audio' (path), 'duration'}] -> one .m4b with chapter marks and the cover."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        lst = Path(td) / 'list.txt'
        _concat_list([c['audio'] for c in chapters], lst)
        meta = Path(td) / 'meta.txt'
        lines = [';FFMETADATA1', f"title={_meta_escape(book['title'])}", f"album={_meta_escape(book['title'])}",
                 f"artist={_meta_escape(book['author'])}", f"album_artist={_meta_escape(book['author'])}",
                 'genre=Audiobook', f"comment={_meta_escape('Made with Third Moon Audiobook Studio')}"]
        if book.get('description'):
            lines.append(f"description={_meta_escape(book['description'][:900])}")
        t = 0
        for c in chapters:
            d = duration(c['audio']) or c['duration']
            lines += ['[CHAPTER]', 'TIMEBASE=1/1000', f'START={int(t * 1000)}', f'END={int((t + d) * 1000)}',
                      f"title={_meta_escape(c['title'])}"]
            t += d
        meta.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        cmd = FF + ['-f', 'concat', '-safe', '0', '-i', str(lst), '-i', str(meta)]
        if cover and Path(cover).exists():
            cmd += ['-i', str(cover), '-map', '0:a', '-map', '2:v', '-c:v', 'mjpeg' if not str(cover).lower().endswith(('.jpg', '.jpeg')) else 'copy',
                    '-disposition:v:0', 'attached_pic']
        else:
            cmd += ['-map', '0:a']
        tmp = out_path.with_suffix('.partial.m4b')
        cmd += ['-map_metadata', '1', '-map_chapters', '1', '-c:a', 'aac', '-b:a', config.get('export_bitrate'),
                '-movflags', '+faststart', '-f', 'mp4', str(tmp)]
        subprocess.run(cmd, check=True)
        tmp.replace(out_path)
    return out_path


def export_mp3s(book, chapters, cover, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    n = len(chapters)
    for i, c in enumerate(chapters, 1):
        name = f'{i:03d} - {safe_name(c["title"])}.mp3'
        out = folder / name
        cmd = FF + ['-i', str(c['audio'])]
        if cover and Path(cover).exists():
            cmd += ['-i', str(cover), '-map', '0:a', '-map', '1:v', '-c:v', 'mjpeg', '-disposition:v:0',
                    'attached_pic', '-id3v2_version', '3']
        cmd += ['-c:a', 'libmp3lame', '-b:a', config.get('export_bitrate'),
                '-metadata', f"title={c['title']}", '-metadata', f"album={book['title']}",
                '-metadata', f"artist={book['author']}", '-metadata', f'track={i}/{n}',
                '-metadata', 'genre=Audiobook', str(out)]
        subprocess.run(cmd, check=True)
        files.append(out)
    zpath = folder.with_suffix('.zip')
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_STORED) as z:
        for f in files:
            z.write(f, f'{folder.name}/{f.name}')
    return folder, zpath
