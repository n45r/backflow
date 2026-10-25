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


def judge_sheet(real_paths, candidates, labels, out_path, cell_w=420):
    """One row per time: the real frame, then one render per candidate (an ordered dict label -> paths)."""
    names = list(candidates)
    assert all(len(candidates[n]) == len(real_paths) for n in names) and len(labels) == len(real_paths)
    font, big = _font(18), _font(22)
    strip_w, head_h, pad = 90, 36, 4
    cols = 1 + len(names)
    rows = []
    for i, rp in enumerate(real_paths):
        imgs = [Image.open(rp).convert("RGB")] + [Image.open(candidates[n][i]).convert("RGB") for n in names]
        imgs = [im.resize((cell_w, round(im.height * cell_w / im.width))) for im in imgs]
        rows.append(imgs)
    W = strip_w + cols * (cell_w + pad) + pad
    H = head_h + sum(max(im.height for im in r) + pad for r in rows)
    sheet = Image.new("RGB", (W, H), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for c, title in enumerate(["Real camera"] + [f"Candidate {n}" for n in names]):
        d.text((strip_w + pad + c * (cell_w + pad) + 8, 6), title, fill="white", font=big)
    y = head_h
    for imgs, lab in zip(rows, labels):
        h = max(im.height for im in imgs)
        d.rectangle([0, y, strip_w, y + h], fill=(40, 40, 60))
        d.text((8, y + h // 2 - 10), str(lab), fill="white", font=font)
        for c, im in enumerate(imgs):
            sheet.paste(im, (strip_w + pad + c * (cell_w + pad), y))
        y += h + pad
    sheet.save(out_path)
    return str(out_path)
