"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds



def run(ds, cfg, preds=None):
    """So nhãn với dự đoán checker, chỉ cảnh báo để người duyệt xem lại."""
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    rules = cfg["second_opinion"]
    issues = []

    for image_path in ds.image_files():
        stem = image_path.stem
        if stem not in preds:
            continue
        lines = ds.read_label_lines(stem)
        if lines is None:
            continue
        size = ds.image_size(stem)
        if size is None:
            continue
        image_width, image_height = size

        # Giữ số dòng gốc; dòng hỏng do check định dạng xử lý riêng.
        labels = []
        for line_no, text in lines:
            try:
                class_id, cx, cy, width, height = parse_yolo_line(text)
            except (ValueError, OverflowError):
                continue
            if 0 <= class_id < len(ds.classes):
                labels.append((line_no, class_id, (cx, cy, width, height)))

        predictions = preds[stem]
        for predicted_class, confidence, cx, cy, width, height in predictions:
            area_px = width * image_width * height * image_height
            if confidence < rules["conf"] or area_px < rules["min_area_px"]:
                continue
            box = (cx, cy, width, height)
            candidates = []
            for _, label_class, label_box in labels:
                overlap = iou_xywh(box, label_box)
                if overlap >= rules["iou_missing"]:
                    candidates.append((label_class, overlap))

            if not candidates:
                issues.append(Issue(
                    "second_opinion", WARN, "POSSIBLE_MISSING", stem,
                    f"model thấy vật lớp {predicted_class}, conf={confidence:.4f}, chưa có box nhãn khớp",
                    extra={"conf": confidence},
                ))
                continue

            same_class = [
                overlap for label_class, overlap in candidates
                if label_class == predicted_class
            ]
            if same_class:
                best_iou = max(same_class)
                if best_iou < rules["iou_loose"]:
                    issues.append(Issue(
                        "second_opinion", WARN, "POSSIBLE_LOOSE_BOX", stem,
                        f"box cùng lớp {predicted_class} khớp lỏng với model: IoU={best_iou:.4f}",
                        extra={"conf": confidence, "iou": best_iou},
                    ))
            else:
                best_iou = max(overlap for _, overlap in candidates)
                if best_iou >= rules["iou_match"]:
                    issues.append(Issue(
                        "second_opinion", WARN, "POSSIBLE_WRONG_CLASS", stem,
                        f"model dự đoán lớp {predicted_class}, nhãn chồng khớp thuộc lớp khác: IoU={best_iou:.4f}",
                        extra={"conf": confidence, "iou": best_iou},
                    ))

        # Nhánh thừa nhãn dùng fp_conf riêng và không lọc diện tích.
        fp_predictions = [row for row in predictions if row[1] >= rules["fp_conf"]]
        for line_no, label_class, label_box in labels:
            overlaps = [iou_xywh(label_box, row[2:]) for row in fp_predictions]
            if not any(overlap >= rules["iou_missing"] for overlap in overlaps):
                best_iou = max(overlaps, default=0.0)
                issues.append(Issue(
                    "second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                    f"box nhãn lớp {label_class} không khớp dự đoán nào đủ fp_conf; IoU tốt nhất={best_iou:.4f}",
                    line=line_no, extra={"iou": best_iou},
                ))

    return issues
