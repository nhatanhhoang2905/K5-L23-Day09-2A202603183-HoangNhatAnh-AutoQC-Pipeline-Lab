"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, ROOT, parse_yolo_line



def fix(ds, issues, cfg):
    """Sửa lỗi bắt buộc trên bản sao dataset và ghi lại từng thay đổi."""
    errors = [issue for issue in issues if issue.severity == ERROR]
    if not errors:
        return []

    raw_root = (ROOT / "data" / "raw").resolve()
    if ds.root.resolve().is_relative_to(raw_root):
        raise ValueError("Không được sửa dữ liệu raw; hãy dùng bản sao dataset.")

    fixes = []

    def record(image, line, action, before, after):
        fixes.append(dict(
            image=image, line=line, action=action, before=before, after=after,
        ))

    # Loại ảnh trước để các lỗi dòng của ảnh đó không còn được xử lý.
    remove_codes = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
    removed = {
        issue.image for issue in errors
        if issue.code in remove_codes or issue.code.startswith("DUP_IMAGE_")
    }
    for stem in sorted(removed):
        paths = [path for path in ds.image_files() if path.stem == stem]
        label_path = ds.label_path(stem)
        if label_path.exists():
            paths.append(label_path)
        if not paths:
            continue
        before = "; ".join(str(path.relative_to(ds.root)) for path in paths)
        for path in paths:
            path.unlink()
        record(stem, None, "remove_image", before, "đã loại ảnh và nhãn")

    if any(issue.code == "BAD_CLASS_NAME" for issue in errors):
        original = ds.yaml_path.read_text(encoding="utf-8") if ds.yaml_path.exists() else ""
        data = yaml.safe_load(original) or {}
        if not isinstance(data, dict):
            data = {}
        names = dict(enumerate(cfg["classes"]))
        if data.get("names") != names and data.get("names") != cfg["classes"]:
            data["names"] = names
            updated = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
            ds.yaml_path.write_text(updated, encoding="utf-8")
            record("data.yaml", None, "rename_classes", original, updated)

    missing = {issue.image for issue in errors if issue.code == "MISSING_LABEL_FILE"}
    for stem in sorted(missing - removed):
        if ds.image_path(stem) is not None and not ds.label_path(stem).exists():
            record(stem, None, "needs_label", "(không có file)", "chuyển người gán")

    # Gom tất cả lỗi theo số dòng gốc trước khi thay đổi nội dung file.
    drops = defaultdict(set)
    clips = defaultdict(set)
    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    for issue in errors:
        if issue.image in removed or issue.line is None:
            continue
        if issue.code in drop_codes:
            drops[issue.image].add(issue.line)
        elif issue.code == "BOX_OUT_OF_IMAGE":
            clips[issue.image].add(issue.line)

    for stem in sorted(set(drops) | set(clips)):
        path = ds.label_path(stem)
        if not path.exists():
            continue
        original_lines = path.read_text(encoding="utf-8").splitlines()
        updated_lines = []
        changed = False
        for line_no, text in enumerate(original_lines, 1):
            if line_no in drops[stem]:
                record(stem, line_no, "drop_line", text, "")
                changed = True
                continue

            if line_no not in clips[stem]:
                updated_lines.append(text)
                continue

            try:
                class_id, cx, cy, width, height = parse_yolo_line(text)
            except (ValueError, OverflowError):
                record(stem, line_no, "drop_line", text, "")
                changed = True
                continue

            left, right = cx - width / 2, cx + width / 2
            top, bottom = cy - height / 2, cy + height / 2
            if 0 <= left < right <= 1 and 0 <= top < bottom <= 1:
                updated_lines.append(text)
                continue

            left, right = max(0.0, left), min(1.0, right)
            top, bottom = max(0.0, top), min(1.0, bottom)
            if right <= left or bottom <= top:
                record(stem, line_no, "drop_line", text, "")
            else:
                clipped = (
                    (left + right) / 2, (top + bottom) / 2,
                    right - left, bottom - top,
                )
                after = f"{class_id} " + " ".join(f"{value:.12g}" for value in clipped)
                updated_lines.append(after)
                record(stem, line_no, "clip_box", text, after)
            changed = True

        if changed:
            content = "\n".join(updated_lines) + ("\n" if updated_lines else "")
            path.write_text(content, encoding="utf-8")

    return fixes
