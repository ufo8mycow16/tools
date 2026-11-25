"""Chatterbox Turbo, loaded once and kept warm.

Same settings as the Vulcan Fury voice scripts (temperature .8, top_p .95, top_k 1000, repetition penalty 1.2,
norm_loudness), but instead of reloading the model for every speaker it keeps each voice's conditioning and swaps
it in - so a chapter that hops between Kirk, Spock and the narrator doesn't reload anything.

Only Turbo's own tags are ever sent:
    [angry] [crying] [dramatic] [fear] [happy] [narration] [sarcastic] [surprised] [whispering]
    [laugh] [chuckle] [gasp] [cough] [sigh] [groan] [sniff] [shush] [clear throat]
"""
import copy
import hashlib
import os
import threading
import time

from . import config, voices

TURBO_TAGS = {'[angry]', '[crying]', '[dramatic]', '[fear]', '[happy]', '[narration]', '[sarcastic]', '[surprised]',
              '[whispering]', '[laugh]', '[chuckle]', '[gasp]', '[cough]', '[sigh]', '[groan]', '[sniff]', '[shush]',
              '[clear throat]'}


class EngineError(Exception):
    pass


class Engine:
    def __init__(self):
        self.model = None
        self.torch = None
        self.sr = 24000
        self.conds = {}
        self.current = None
        self.lock = threading.Lock()
        self.last_used = 0
        self.device = ''
        self.fake = os.environ.get('AUDIOBOOK_FAKE_TTS') == '1'

    def status(self):
        return {'loaded': self.model is not None or (self.fake and self.current is not None),
                'device': self.device or ('test' if self.fake else ''), 'voices_ready': len(self.conds),
                'fake': self.fake}

    def load(self):
        if self.model is not None or self.fake:
            return
        try:
            import torch
            from chatterbox.tts_turbo import ChatterboxTurboTTS
        except ImportError as e:
            raise EngineError(
                "Chatterbox isn't installed in the Python running the studio. Start it with "
                "START_AUDIOBOOK_STUDIO.bat (it uses " + str(config.path('chatterbox_root') / 'venv') + "). "
                f"({e})")
        dev = config.get('device')
        if dev == 'auto':
            dev = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.torch = torch
        self.device = dev
        self.model = ChatterboxTurboTTS.from_pretrained(device=dev)
        self.sr = getattr(self.model, 'sr', getattr(self.model, 'sample_rate', 24000))

    def unload(self):
        with self.lock:
            self.model = None
            self.conds.clear()
            self.current = None
            if self.torch is not None and self.torch.cuda.is_available():
                self.torch.cuda.empty_cache()

    def _use_voice(self, key):
        if self.current == key:
            return
        ref = voices.conditioning_wav(key)
        if self.fake:
            self.current = key
            return
        stamp = voices.voice_hash(key)
        cached = self.conds.get(key)
        if cached and cached[0] == stamp:
            try:
                self.model.conds = copy.deepcopy(cached[1])
                self.current = key
                return
            except Exception:
                pass
        self.model.prepare_conditionals(str(ref))
        try:
            self.conds[key] = (stamp, copy.deepcopy(self.model.conds))
        except Exception:
            self.conds.pop(key, None)
        self.current = key

    def speak(self, text, voice_key, seed_text=None):
        """-> (numpy float32 array, sample rate)"""
        with self.lock:
            self.load()
            self._use_voice(voice_key)
            self.last_used = time.time()
            seed = int.from_bytes(hashlib.sha256((seed_text or text).encode()).digest()[:4], 'little')
            if self.fake:
                return _fake_audio(text, seed), 24000
            torch = self.torch
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
            with torch.inference_mode():
                audio = self.model.generate(text, temperature=float(config.get('temperature')),
                                            top_p=float(config.get('top_p')), top_k=int(config.get('top_k')),
                                            repetition_penalty=float(config.get('repetition_penalty')),
                                            norm_loudness=True)
            import numpy as np
            if isinstance(audio, torch.Tensor):
                audio = audio.detach().float().cpu().numpy()
            a = np.nan_to_num(np.asarray(audio, dtype=np.float32).squeeze())
            if a.ndim != 1 or not a.size:
                raise EngineError('Chatterbox gave back no audio for: ' + text[:80])
            peak = float(np.max(np.abs(a)))
            if peak > 1:
                a = a / peak
            return trim_silence(a, self.sr), self.sr


def trim_silence(a, sr, threshold=0.012, keep=0.06):
    """Cut dead air off both ends (Turbo sometimes leaves a breath of silence), keeping a tiny cushion."""
    import numpy as np
    loud = np.where(np.abs(a) > threshold)[0]
    if not loud.size:
        return a
    pad = int(sr * keep)
    return a[max(0, loud[0] - pad):min(len(a), loud[-1] + pad)]


def _fake_audio(text, seed):
    """Test mode only (AUDIOBOOK_FAKE_TTS=1): a quiet hum the length speech would be, so the app can be checked
    without Chatterbox."""
    import numpy as np
    sr = 24000
    secs = max(0.4, len(text) / 15.0)
    t = np.arange(int(sr * secs)) / sr
    f = 110 + (seed % 200)
    return (0.1 * np.sin(2 * np.pi * f * t) * np.minimum(1, np.minimum(t, secs - t) * 10)).astype('float32')


ENGINE = Engine()


def build_prompt(text, tags):
    tags = [t for t in tags if t in TURBO_TAGS]
    return (' '.join(tags) + ' ' + text).strip() if tags else text
