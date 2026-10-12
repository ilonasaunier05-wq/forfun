"""RMS envelope of the actual PCM decoded for playback (no microphone loopback)."""
import numpy as np


def pcm_envelope(raw, sample_rate, sample_format=-16, channels=2, fps=30):
    if sample_format not in {-16, 16, -8, 8, -32, 32} or sample_rate <= 0 or channels <= 0:
        return []
    width = abs(sample_format) // 8
    dtype = ('<' if width > 1 else '') + ('i' if sample_format < 0 else 'u') + str(width)
    data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    scale = float(2 ** (abs(sample_format) - 1))
    if sample_format > 0: data -= scale
    data /= scale
    window = max(1, int(sample_rate / fps)) * channels
    return [min(1.0, float(np.sqrt(np.mean(data[i:i+window] ** 2))) * 4) for i in range(0, len(data), window)]
