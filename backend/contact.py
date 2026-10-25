from PIL import Image, ImageDraw, ImageFont


def _font(size):
    for p in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def contact_sheet(real_paths, render_paths, labels, out_path, cell_w=640):
    assert len(real_paths) == len(render_paths) == len(labels)
    font, big = _font(18), _font(22)
    strip_w, head_h, pad = 90, 36, 4
    rows = []
    for rp, sp in zip(real_paths, render_paths):
        a, b = Image.open(rp).convert("RGB"), Image.open(sp).convert("RGB")
        a = a.resize((cell_w, round(a.height * cell_w / a.width)))
        b = b.resize((cell_w, round(b.height * cell_w / b.width)))
        rows.append((a, b))
    W = strip_w + 2 * cell_w + 3 * pad
    H = head_h + sum(max(a.height, b.height) + pad for a, b in rows)
    sheet = Image.new("RGB", (W, H), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    d.text((strip_w + pad + 8, 6), "Real camera", fill="white", font=big)
    d.text((strip_w + 2 * pad + cell_w + 8, 6), "Simulation render", fill="white", font=big)
    y = head_h
    for (a, b), lab in zip(rows, labels):
        h = max(a.height, b.height)
        d.rectangle([0, y, strip_w, y + h], fill=(40, 40, 60))
        d.text((8, y + h // 2 - 10), str(lab), fill="white", font=font)
        sheet.paste(a, (strip_w + pad, y))
        sheet.paste(b, (strip_w + 2 * pad + cell_w, y))
        y += h + pad
    sheet.save(out_path)
    return str(out_path)
