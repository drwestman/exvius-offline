"""Pure native detail-image fitting, following pinned revival banner_fit blur2."""
import io

FRAMES = {'paid': (640, 183), 'base': (640, 392)}
PIPELINE = 1
TOLERANCE = .06


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
    from PIL import Image, ImageEnhance, ImageFilter
    size = inspect(raw)
    canvas = dimensions(size, mode)
    if canvas == size:
        return raw
    with Image.open(io.BytesIO(raw)) as image:
        width, height = size
        scale = max(canvas[0] / width, canvas[1] / height)
        cover = image.convert('RGB').resize((max(1, round(width * scale)), max(1, round(height * scale))),
                                             Image.Resampling.BILINEAR)
        left, top = (cover.width - canvas[0]) // 2, (cover.height - canvas[1]) // 2
        cover = cover.crop((left, top, left + canvas[0], top + canvas[1]))
        cover = cover.filter(ImageFilter.GaussianBlur(max(4, canvas[1] // 14)))
        out = ImageEnhance.Brightness(cover).enhance(.45).convert('RGBA')
        original = image.convert('RGBA')
        out.paste(original, ((canvas[0] - width) // 2, (canvas[1] - height) // 2), original)
        result = io.BytesIO()
        out.save(result, 'PNG', optimize=True)
        return result.getvalue()
