"""기획서 "4주 개발 계획" 그림을 만든다.

칸 내용은 아래 TITLE, ROWS, MILESTONES만 고치면 된다.
행은 2개(ROW_Y), 행마다 칸은 WEEKS 수(4개)에 맞춰야 한다. 다르면 오류로 알려 준다.
실행: python docs/plan/figures/plan_4weeks.py <저장할 png 경로>
필요: pip install -r docs/plan/figures/requirements.txt
글꼴: 환경 변수 PLAN_FONT가 있으면 그 파일, 없으면 FONT_CANDIDATES에서 처음 찾은 것
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

TITLE = "2주차 끝에 등기부 추출을, 4주차 끝에 계약 전부터 다음 집까지 검증한다"
WEEKS = ["1주차", "2주차", "3주차", "4주차"]
ROWS = [
    ("A · 백엔드·규칙", "파싱, 규칙, 계산", [
        ("등기부 요약 파싱", "샘플 3건 · 판정 기준 명세"),
        ("판정 규칙 · 실거래 API", "규칙 3개 · 주변 시세 수집"),
        ("할 일 엔진 · 갈아타기", "9종 · 특약 분기 · 시나리오 10개"),
        ("역전세 경보 · 통합", "경보 재계산 · 경보 정답표"),
    ]),
    ("B · 프론트·검증", "화면, 기록함, 사용성 테스트", [
        ("화면 설계", "동작 5개 · 정적 4개"),
        ("계약 전·계약 당일 화면", "시연 집 2채 매칭 · 특약 기록"),
        ("기록함 · 알림", "업로드 · 이메일 1종 · ICS"),
        ("만기·갈아타기 화면", "사용성 테스트 5명"),
    ]),
]
# (주차 경계 번호: 1이면 1주차 끝, 칸 위치), 제목, 설명, 강조색 여부
MILESTONES = [
    (2, "중간 점검", "등기부 요약 추출 95%", False),
    (4, "최종 시연", "집 2채 · 계약 전부터 다음 집까지 5분", True),
]

S = 2                      # 2배로 그려 선명하게
W, H = 1344, 600
FONT_CANDIDATES = [
    "C:/Windows/Fonts/NotoSansKR-VF.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/NotoSansKR-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]
INK, SUB, LINE, BOX = "#1F1F1F", "#6B6B6B", "#C9C5BD", "#C9C5BD"
GRAY_MARK, BLUE = "#D3CFC7", "#2F6FD6"

COL_X0, COL_W, COL_GAP = 295, 232, 22
ROW_Y = [157, 287]
BOX_H = 98


def find_font():
    paths = [os.environ["PLAN_FONT"]] if os.environ.get("PLAN_FONT") else FONT_CANDIDATES
    for p in paths:
        if os.path.exists(p):
            return p
    raise SystemExit("한글 글꼴을 찾지 못했다. PLAN_FONT=<글꼴 파일 경로>로 지정하세요.")


FONT = find_font()


def check_layout():
    if len(ROWS) > len(ROW_Y):
        raise SystemExit(f"행은 {len(ROW_Y)}개까지다. 더 넣으려면 ROW_Y와 H를 늘리세요.")
    for label, _, cells in ROWS:
        if len(cells) != len(WEEKS):
            raise SystemExit(f"'{label}' 행의 칸이 {len(cells)}개다. WEEKS({len(WEEKS)}개)와 같아야 한다.")


def font(size, weight=400):
    # Apple SD Gothic Neo는 굵기가 파일 안의 별도 글꼴(6번이 Bold)이라 따로 고른다
    bold_index = 6 if weight >= 700 and FONT.endswith("AppleSDGothicNeo.ttc") else 0
    f = ImageFont.truetype(FONT, size * S, index=bold_index)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def col_left(i):
    return COL_X0 + i * (COL_W + COL_GAP)


def boundary_x(week_end):
    """week_end 주차 끝 경계선의 x (4주차 끝은 오른쪽 끝)."""
    if week_end == len(WEEKS):
        return col_left(len(WEEKS) - 1) + COL_W + 13
    return col_left(week_end) - COL_GAP / 2


def dashed_v(d, x, y0, y1, color, width=2, dash=6, gap=5):
    y = y0
    while y < y1:
        d.line([(x * S, y * S), (x * S, min(y + dash, y1) * S)], fill=color, width=width * S)
        y += dash + gap


def text(d, xy, s, f, fill, anchor="la"):
    d.text((xy[0] * S, xy[1] * S), s, font=f, fill=fill, anchor=anchor)


def draw(path):
    check_layout()
    img = Image.new("RGB", (W * S, H * S), "white")
    d = ImageDraw.Draw(img)

    text(d, (40, 50), TITLE, font(26, 700), INK, "lm")

    for i, w in enumerate(WEEKS):
        text(d, (col_left(i) + COL_W / 2, 118), w, font(18, 400), "#3A3A3A", "mm")
    d.line([(285 * S, 140 * S), ((boundary_x(len(WEEKS))) * S, 140 * S)], fill=LINE, width=2 * S)

    marks = {m[0] for m in MILESTONES}
    for week_end in range(1, len(WEEKS)):
        x = boundary_x(week_end)
        if week_end in marks:
            dashed_v(d, x, 140, 428, "#B5B1A9")
        else:
            d.line([(x * S, 140 * S), (x * S, 400 * S)], fill=LINE, width=2 * S)

    for r, (label, sub, cells) in enumerate(ROWS):
        y = ROW_Y[r]
        text(d, (40, y + 35), label, font(20, 700), INK, "lm")
        text(d, (40, y + 68), sub, font(16, 400), SUB, "lm")
        for i, (t, s) in enumerate(cells):
            x = col_left(i)
            d.rounded_rectangle([x * S, y * S, (x + COL_W) * S, (y + BOX_H) * S], radius=14 * S,
                                outline=BOX, width=2 * S, fill="white")
            text(d, (x + COL_W / 2, y + 36), t, font(19, 700), INK, "mm")
            text(d, (x + COL_W / 2, y + 71), s, font(14, 400), SUB, "mm")

    for week_end, title, desc, strong in MILESTONES:
        x = boundary_x(week_end)
        color = BLUE if strong else GRAY_MARK
        if strong:
            dashed_v(d, x, 140, 428, BLUE)
        r = 15
        d.polygon([(x * S, (442 - r) * S), ((x + r) * S, 442 * S), (x * S, (442 + r) * S), ((x - r) * S, 442 * S)], fill=color)
        anchor_x, anchor = (x, "m") if week_end < len(WEEKS) else (W - 22, "r")
        text(d, (anchor_x, 492), title, font(17, 700), INK, anchor + "m")
        text(d, (anchor_x, 525), desc, font(15, 400), SUB, anchor + "m")

    img.save(path)


if __name__ == "__main__":
    draw(sys.argv[1] if len(sys.argv) > 1 else "plan_4weeks.png")
