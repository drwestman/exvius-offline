"""Pure native detail-image fitting, following pinned revival banner_fit blur2."""
from collections.abc import Iterator
from dataclasses import dataclass
import io
from typing import ClassVar, Protocol

FRAMES = {'paid': (640, 183), 'base': (640, 392)}
PIPELINE = 2
TOLERANCE = .06


@dataclass(frozen=True)
class RenderedFrame:
    """One rendered PNG payload for a single target frame mode."""
    mode: str
    raw: bytes


class BannerFrameRenderer(Protocol):
    """Pure frame rendering contract: yield one RenderedFrame per requested mode."""

    @property
    def pipeline(self) -> int: ...

    def render_frames(self, raw: bytes, modes: tuple[str, ...]) -> Iterator[RenderedFrame]: ...


@dataclass(frozen=True)
class PillowBannerFrameRenderer:
    """Lossless Pillow frame renderer using fast zlib compression without PNG optimizer sweeps."""
    compress_level: ClassVar[int] = 6
    optimize: ClassVar[bool] = False

    @property
    def pipeline(self) -> int:
        return PIPELINE

    def render_frames(self, raw: bytes, modes: tuple[str, ...]) -> Iterator[RenderedFrame]:
        """Validate source PNG bytes once and yield one RenderedFrame per requested mode."""
        size = inspect(raw)
        targets = tuple((mode, dimensions(size, mode)) for mode in modes)
        return self._render_plan(raw, size, targets)

    def _render_plan(
        self,
        raw: bytes,
        size: tuple[int, int],
        targets: tuple[tuple[str, tuple[int, int]], ...],
    ) -> Iterator[RenderedFrame]:
        if not any(canvas != size for _, canvas in targets):
            for mode, _ in targets:
                yield RenderedFrame(mode, raw)
            return
        from PIL import Image, ImageEnhance, ImageFilter
        with Image.open(io.BytesIO(raw)) as image:
            original = image.convert('RGBA')
            # P-mode PNGs with byte tRNS convert through RGBA without losing palette RGB values or warning.
            rgb = (original.convert('RGB')
                   if image.mode == 'P' and isinstance(image.info.get('transparency'), bytes)
                   else image.convert('RGB'))
            width, height = size
            for mode, canvas in targets:
                if canvas == size:
                    yield RenderedFrame(mode, raw)
                    continue
                scale = max(canvas[0] / width, canvas[1] / height)
                cover = rgb.resize((max(1, round(width * scale)), max(1, round(height * scale))),
                                   Image.Resampling.BILINEAR)
                left, top = (cover.width - canvas[0]) // 2, (cover.height - canvas[1]) // 2
                cover = cover.crop((left, top, left + canvas[0], top + canvas[1]))
                cover = cover.filter(ImageFilter.GaussianBlur(max(4, canvas[1] // 14)))
                out = ImageEnhance.Brightness(cover).enhance(.45).convert('RGBA')
                out.paste(original, ((canvas[0] - width) // 2, (canvas[1] - height) // 2), original)
                result = io.BytesIO()
                out.save(result, 'PNG', optimize=self.optimize, compress_level=self.compress_level)
                yield RenderedFrame(mode, result.getvalue())


DEFAULT_RENDERER = PillowBannerFrameRenderer()


def inspect(raw):
    from PIL import Image
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != 'PNG' or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('expected one native PNG image')
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            return image.size
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError(f'Invalid summon PNG: {exc}') from exc


def dimensions(size, mode):
    width, height = size
    target = FRAMES[mode][0] / FRAMES[mode][1]
    if width <= 0 or height <= 0:
        raise ValueError('Invalid summon image dimensions')
    if abs(width / height - target) / target <= TOLERANCE:
        return size
    return (width, round(width / target)) if width / height > target else (round(height * target), height)


def render(raw, mode):
    """Keep every source pixel at its native scale, centered over blurred padding."""
    return next(DEFAULT_RENDERER.render_frames(raw, (mode,))).raw
