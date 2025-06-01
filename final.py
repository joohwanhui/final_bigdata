import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
from datetime import datetime, timedelta
from collections import defaultdict
import sys

# —————————————————————————————————————————————————————————
# 경고 메시지 무시 설정 (XML 문서를 HTML 파서로 파싱할 때 발생하는 경고 억제)
# —————————————————————————————————————————————————————————
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# —————————————————————————————————————————————————————————
# 1) 확장된 지역명 ↔ 기상청 격자 좌표 매핑 (예시)
# —————————————————————————————————————————————————————————
REGION_GRID = {
    # 수도권
    '서울':    (60, 127),
    '인천':    (55, 124),
    '수원':    (60, 120),
    '의정부':  (61, 125),
    '이천':    (60, 121),
    '파주':    (56, 131),

    # 강원도
    '춘천':    (67, 115),
    '강릉':    (92, 132),
    '속초':    (102, 139),
    '원주':    (61, 121),
    '태백':    (79, 137),

    # 충청북도
    '청주':    (69, 107),
    '충주':    (69, 126),
    '제천':    (74, 134),

    # 충청남도
    '대전':    (67, 100),
    '천안':    (64, 107),
    '공주':    (65, 111),
    '보령':    (62, 80),
    '서산':    (53, 95),

    # 전라북도
    '전주':    (63, 89),
    '군산':    (62, 84),
    '남원':    (60, 77),

    # 전라남도
    '광주':    (58, 74),
    '여수':    (69, 62),
    '순천':    (55, 74),
    '목포':    (51, 58),

    # 경상북도
    '대구':    (89, 90),
    '포항':    (98, 87),
    '경주':    (89, 83),
    '안동':    (89, 103),
    '울진':    (105, 106),

    # 경상남도
    '부산':    (97, 74),
    '울산':    (102, 84),
    '창원':    (89, 73),
    '거제':    (95, 76),
    '통영':    (92, 74),

    # 제주도
    '제주':    (52, 38),
    '서귀포':  (52, 36),
}

# —————————————————————————————————————————————————————————
# 2) 기상청 동네예보 RSS에서 일자별 최대 강수확률(pop)을 가져오는 함수
# —————————————————————————————————————————————————————————
def fetch_daily_max_pop(gridx: int, gridy: int) -> dict:
    """
    기상청 동네예보 RSS(queryDFS.jsp)를 호출하여,
    오늘(0)부터 6일차(6)까지의 일별 최대 강수확률을 반환한다.
    반환 형식: { day_offset(int 0~6): max_pop(int 0~100), ... }
    """
    url = "https://www.kma.go.kr/wid/queryDFS.jsp"
    resp = requests.get(url, params={"gridx": gridx, "gridy": gridy})
    resp.encoding = 'utf-8'
    resp.raise_for_status()

    # BeautifulSoup 경고는 위에서 무시하도록 설정했으므로 'html.parser'로 그대로 사용해도 경고가 발생하지 않습니다.
    soup = BeautifulSoup(resp.text, 'html.parser')
    data_nodes = soup.find_all('data')

    pops_by_day = defaultdict(int)
    for node in data_nodes:
        day_off = int(node.find('day').text)    # 0: 오늘, 1: 내일, ...
        pop = int(node.find('pop').text)        # 해당 시각 강수확률
        if 0 <= day_off < 7:
            pops_by_day[day_off] = max(pops_by_day[day_off], pop)

    return {d: pops_by_day.get(d, 0) for d in range(7)}

# —————————————————————————————————————————————————————————
# 3) 연속된 “맑은 날(강수확률<10%)” 구간을 찾아주는 함수
# —————————————————————————————————————————————————————————
def find_clear_sequences(max_pops: dict) -> list:
    """
    max_pops: {0:pop0, 1:pop1, …, 6:pop6}
    pop < 10 → “맑음”, pop ≥ 10 → “비옴”.
    연속된 맑은 날(일차 번호)들을 리스트로 묶어 반환.
    예) max_pops = {0:5, 1:0, 2:60, 3:8, 4:0, 5:0, 6:15}
       반환: [[0, 1], [3, 4, 5]]
    """
    sequences = []
    current_seq = []

    for day_off in range(7):
        pop = max_pops.get(day_off, 0)
        if pop < 10:   # “맑음” 조건
            current_seq.append(day_off)
        else:
            if current_seq:
                sequences.append(current_seq)
                current_seq = []
    if current_seq:
        sequences.append(current_seq)

    return sequences

# —————————————————————————————————————————————————————————
# 4) 메뉴 1: 특정 지역의 “연속된 맑은 날” 추천 (추천 후 종료)
#    - 설명 문구 없이 간단히 날짜 목록만 출력
# —————————————————————————————————————————————————————————
def menu_recommend_dates_for_region():
    print("\n[여행가기 좋은 날 추천]")
    region = input("가고 싶은 지역명을 입력하세요 (예: 서울) ▶ ").strip()
    if region not in REGION_GRID:
        print(f"⚠️ 등록된 지역이 아닙니다: \"{region}\"")
        print("   사용 가능한 지역 목록:", ", ".join(REGION_GRID.keys()))
        sys.exit(0)

    gridx, gridy = REGION_GRID[region]
    max_pops = fetch_daily_max_pop(gridx, gridy)
    sequences = find_clear_sequences(max_pops)

    today = datetime.now().date()

    if not sequences:
        print(f"\n{region} 지역에는 앞으로 7일간 맑은 연속 구간이 없습니다.")
        sys.exit(0)

    print(f"\n🎉 {region} 지역의 연속된 맑은 날:")
    for seq in sequences:
        start_off = seq[0]
        end_off = seq[-1]
        start_date = today + timedelta(days=start_off)
        end_date = today + timedelta(days=end_off)

        if start_off == end_off:
            print(f"  • {start_date} (단일 맑음)")
        else:
            print(f"  • {start_date} ~ {end_date} (연속 {len(seq)}일 맑음)")
    sys.exit(0)

# —————————————————————————————————————————————————————————
# 5) 메뉴 2: 날짜 범위 내 “맑은 날”이 가장 많은 지역 추천 (상위 3개만 출력)
#    - pop_sum 없이, 지역명만 출력
# —————————————————————————————————————————————————————————
def menu_recommend_region_for_dates():
    print("\n[여행가기 좋은 지역 추천]")
    print("날짜 입력 형식 예시: 3.21-3.25  (월.일-월.일)")
    date_range = input("몇월 며칠부터 몇월 며칠까지 ▶ ").strip()

    try:
        start_str, end_str = date_range.split('-')
        sm, sd = start_str.split('.')
        em, ed = end_str.split('.')
        year = datetime.now().year

        start_date = datetime(year=year, month=int(sm), day=int(sd)).date()
        end_date   = datetime(year=year, month=int(em), day=int(ed)).date()
    except Exception:
        print("⚠️ 날짜 형식이 올바르지 않습니다. 예시: 3.21-3.25")
        sys.exit(0)

    if end_date < start_date:
        print("⚠️ 종료일이 시작일보다 앞설 수 없습니다.")
        sys.exit(0)

    today = datetime.now().date()
    delta0 = (start_date - today).days
    delta1 = (end_date - today).days

    # 0~6일차 예보 범위 밖이면 오류 처리
    if delta1 < 0 or delta0 > 6:
        print("\n⚠️ 입력하신 날짜가 앞으로 7일 예보 범위를 벗어났습니다.")
        sys.exit(0)

    # 예보 가능 일차(0~6) 리스트로 추출
    day_offsets = [d for d in range(delta0, delta1 + 1) if 0 <= d < 7]
    if not day_offsets:
        print("\n⚠️ 입력하신 날짜 중 예보 가능한 날짜가 없습니다.")
        sys.exit(0)

    # 1) 각 지역별로 “맑은 날(강수확률<10%)” 개수만 기록
    region_clear_counts = {}
    max_clear_days = -1

    for region, (gx, gy) in REGION_GRID.items():
        max_pops = fetch_daily_max_pop(gx, gy)
        clear_count = sum(1 for d in day_offsets if max_pops.get(d, 0) < 10)
        region_clear_counts[region] = clear_count
        if clear_count > max_clear_days:
            max_clear_days = clear_count

    if max_clear_days <= 0:
        print("\n⚠️ 해당 기간 내 맑은 날(강수확률<10%)이 없습니다.")
        sys.exit(0)

    # 2) “맑은 날 개수”가 최대인 지역들만 추려낸 뒤, 상위 3개만 출력
    candidates = [r for r, cnt in region_clear_counts.items() if cnt == max_clear_days]
    top3 = candidates[:3]  # 후보군이 3개 이상일 경우, 그냥 첫 3개만

    # 3) 결과 출력
    print(f"\n🎉 '{start_date} ~ {end_date}' 기간 중 맑은 날이 가장 많은 지역 (총 {max_clear_days}일):")
    for idx, r in enumerate(top3, start=1):
        print(f"  {idx}. {r}")
    print()
    sys.exit(0)

# —————————————————————————————————————————————————————————
# 6) 메인 메뉴 (메뉴 3 삭제, 종료 옵션만 유지)
# —————————————————————————————————————————————————————————
def main_menu():
    while True:
        print("\n==============================")
        print(" 원하시는 메뉴를 선택해주세요:")
        print(" 1. 여행가기 좋은 날 추천")
        print(" 2. 여행가기 좋은 지역 추천")
        print(" 0. 종료")
        print("==============================")
        choice = input("메뉴 번호 입력 ▶ ").strip()

        if choice == '1':
            menu_recommend_dates_for_region()
        elif choice == '2':
            menu_recommend_region_for_dates()
        elif choice == '0':
            print("프로그램을 종료합니다. 감사합니다!")
            break
        else:
            print("⚠️ 올바른 메뉴 번호(0, 1, 2)를 입력해주세요.")

if __name__ == "__main__":
    print("==========================================")
    print("   ✈️  여행 스케줄러 v2.3  ✈️")
    print("   (pop_sum 및 추가 설명문구 제거, 메뉴 3 삭제)")
    print("==========================================")
    main_menu()