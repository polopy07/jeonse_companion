"""등기부 PDF → 요약 페이지 글자 (pdfplumber)."""
import io

import pdfplumber

from app.registry.parser import TITLE, RegistryParseError, RegistrySummary, parse_summary_text

LINE_TOLERANCE = 3   # 같은 줄로 보는 글자 높이 차이 (pt)
SPACE_GAP = 3        # 이보다 벌어지면 띄어쓰기 (pt)


def page_text(page) -> str:
    """페이지 글자를 위에서 아래 줄 순서로 만든다.

    pdfplumber 기본 추출은 한 줄 안의 글자를 x 좌표로 정렬한다. 인터넷등기소 "부동산정보요약"을 브라우저에서
    PDF로 저장하면 을구 표의 근저당권자 칸이 대상소유자 칸까지 넘쳐 두 칸 글자가 x 좌표로 섞인다
    ("주식회사부○산○은○행"). 그래서 한 줄 안에서는 PDF에 적힌 순서를 지키고, 왼쪽으로 되돌아가는 곳에서
    끊은 조각들만 시작 위치로 정렬한다.
    """
    lines: list[tuple[float, list[dict]]] = []
    for c in page.chars:
        for top, chars in lines:
            if abs(top - c["top"]) <= LINE_TOLERANCE:
                chars.append(c)
                break
        else:
            lines.append((c["top"], [c]))

    out = []
    for _, chars in sorted(lines, key=lambda line: line[0]):
        runs: list[list[dict]] = []
        for c in chars:
            if runs and c["x0"] >= runs[-1][-1]["x0"]:
                runs[-1].append(c)
            else:
                runs.append([c])
        pieces = []
        for run in sorted(runs, key=lambda r: r[0]["x0"]):
            text = run[0]["text"]
            for prev, c in zip(run, run[1:]):
                text += (" " if c["x0"] - prev["x1"] > SPACE_GAP else "") + c["text"]
            pieces.append(text)
        line = " ".join(" ".join(pieces).split())   # PDF의 띄어쓰기 글자와 간격으로 생긴 공백을 하나로
        if line:
            out.append(line)
    return "\n".join(out)


def extract_summary_text(pdf: bytes) -> str:
    """요약 제목이 처음 나오는 페이지부터 끝까지의 글자 (요약이 두 페이지 이상에 걸칠 수 있음)."""
    try:
        with pdfplumber.open(io.BytesIO(pdf)) as doc:
            pages = [page_text(page) for page in doc.pages]
    except Exception as e:  # pdfminer는 깨진 파일마다 다른 예외를 낸다
        raise RegistryParseError("PDF를 열 수 없습니다") from e

    if not any(p.strip() for p in pages):
        raise RegistryParseError("PDF에서 글자를 읽을 수 없습니다 (스캔한 이미지 PDF는 지원하지 않음)")

    start = next((i for i, p in enumerate(pages) if TITLE.search(p)), None)
    if start is None:
        raise RegistryParseError(RegistryParseError.NO_SUMMARY)
    return "\n".join(pages[start:])


def parse_registry_pdf(pdf: bytes) -> RegistrySummary:
    return parse_summary_text(extract_summary_text(pdf))
