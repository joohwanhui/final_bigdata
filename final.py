import requests
from datetime import datetime, timedelta
import urllib.request, urllib.parse, json, sys, re
from collections import defaultdict
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# ——————————————————————————————————————————————
# 0) KMA 동네예보 지역 목록 로딩 (읍·면·동 단위)
#    HTTP로만 정상 동작하며 실패 시 광역시 폴백
# ——————————————————————————————————————————————
def load_kma_regions():
    # 반드시 http:// 로만 접근해야 JSON이 정상으로 내려옵니다.
    url = "http://www.kma.go.kr/DFSROOT/POINT/DATA/top.json.txt"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        # 이 부분이 핵심: 이 줄에서 JSONDecodeError 없이 파싱되어야 전국 읍·면·동이 로드됩니다.
        tree = resp.json()
    except Exception:
        # JSON 파싱에 실패하면 폴백(광역시 7개)만 남습니다.
        return ['서울','부산','인천','대구','광주','울산','제주']

    regions = []
    def recurse(node):
        name = node.get("local")
        if name:
            regions.append(name)
        for child in node.get("children", []):
            recurse(child)
    recurse(tree)
    return regions

REGIONS = load_kma_regions()

# ——————————————————————————————————————————————
# 1) Visual Crossing 날씨 타임라인 API (최대 30일)
# ——————————————————————————————————————————————
VC_API_KEY = "2L3JELGRGWJHR4C8Q2BDDFN3U"

def fetch_timeline(region, start, end):
    loc = urllib.parse.quote(f"{region},KR")
    url = (
        f"https://weather.visualcrossing.com/VisualCrossingWebServices/"
        f"rest/services/timeline/{loc}/{start}/{end}"
        f"?unitGroup=metric&include=days&key={VC_API_KEY}&contentType=json"
    )
    r = requests.get(url)
    r.raise_for_status()
    return r.json().get("days", [])

# ——————————————————————————————————————————————
# 2) OpenWeatherMap 미세먼지 예보
# ——————————————————————————————————————————————
OWM_API_KEY = "YOUR_OPENWEATHERMAP_KEY"
REGION_COORD = {
    '서울': (37.5665,126.9780), '부산': (35.1796,129.0756),
    '인천': (37.4563,126.7052), '대구': (35.8714,128.6014),
    '광주': (35.1595,126.8526), '울산': (35.5384,129.3114),
    '제주': (33.4996,126.5312),
}

def fetch_air_pollution(lat, lon):
    data = requests.get(
        "http://api.openweathermap.org/data/2.5/air_pollution/forecast",
        params={"lat":lat,"lon":lon,"appid":OWM_API_KEY}
    ).json().get("list", [])
    daily = defaultdict(lambda: {"pm2_5": [], "pm10": []})
    for e in data:
        dt = datetime.utcfromtimestamp(e["dt"]) + timedelta(hours=9)
        d = dt.date().isoformat()
        c = e["components"]
        daily[d]["pm2_5"].append(c.get("pm2_5", 0))
        daily[d]["pm10"].append(c.get("pm10", 0))
    return {d: {"pm2_5": sum(v["pm2_5"])/len(v["pm2_5"]),
                "pm10":  sum(v["pm10"])/len(v["pm10"])}
            for d, v in daily.items()}

# ——————————————————————————————————————————————
# 3) 네이버 블로그 맛집 검색
# ——————————————————————————————————————————————
NAVER_CLIENT_ID     = "jh4j9OLJJV71zlU6TiBn"
NAVER_CLIENT_SECRET = "3uNogYwcqj"

def clean_html(raw):
    return re.sub(r'<.*?>', '', raw)

def search_blog(query):
    enc = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/blog?query={enc}&display=5"
    req = urllib.request.Request(url)
    req.add_header("X-Naver-Client-Id", NAVER_CLIENT_ID)
    req.add_header("X-Naver-Client-Secret", NAVER_CLIENT_SECRET)
    with urllib.request.urlopen(req) as res:
        if res.getcode() != 200:
            return []
        data = json.loads(res.read().decode())
    return [{
        "title": clean_html(item["title"]),
        "link":  item["link"],
        "blogger": item["bloggername"],
        "date":   item["postdate"],
        "desc":   clean_html(item["description"])
    } for item in data.get("items",[])]

# ——————————————————————————————————————————————
# 메뉴 1-1: 날짜 → 지역 추천 (강수확률<10%)
# ——————————————————————————————————————————————
def menu_precip_regions():
    today = datetime.now().date()
    start, end = today.isoformat(), (today + timedelta(days=29)).isoformat()
    max_date = today + timedelta(days=29)
    print(f"👉 최대 예보일자: {max_date.month}.{max_date.day} (총 30일치)")

    dr = input("\n[1-1] 날짜 입력 (예: 6.10-6.24 or 6.15) ▶ ").strip()
    try:
        def to_off(p):
            m, d = p.split('.')
            return (datetime(today.year, int(m), int(d)).date() - today).days
        if '-' in dr:
            a, b = dr.split('-')
            offs = list(range(to_off(a), to_off(b) + 1))
        else:
            offs = [to_off(dr)]
    except:
        print("형식 오류 – 예시(6.10-6.24 or 6.15)를 참고하세요.")
        return

    if any(o < 0 or o > 29 for o in offs):
        print("\n예보 범위를 벗어났습니다!")
        return

    stats = []
    for region in REGIONS:
        try:
            days = fetch_timeline(region, start, end)
            cnt = sum(1 for o in offs if days[o]["precipprob"] < 10)
            stats.append((region, cnt))
        except:
            continue

    if not stats:
        print("조회 가능한 지역이 없습니다.")
        return

    mx = max(c for _, c in stats)
    if mx == 0:
        print("\n해당 기간에는 맑은 지역이 없습니다!")
        return

    print("\n▶ 맑은 날 최다 지역 Top3:")
    for r, c in sorted(stats, key=lambda x: -x[1])[:3]:
        print(f" • {r} ({c}일)")

# ——————————————————————————————————————————————
# 메뉴 1-2: 지역 → 날짜 추천 (연속 맑은 구간)
# ——————————————————————————————————————————————
def menu_precip_dates():
    today = datetime.now().date()
    start, end = today.isoformat(), (today + timedelta(days=29)).isoformat()

    user = input("\n[1-2] 지역 입력 ▶ ").strip()
    candidates = [r for r in REGIONS if user in r]
    if not candidates:
        print("등록되지 않은 지역입니다!")
        return
    region = candidates[0]

    days = fetch_timeline(region, start, end)
    seqs, cur = [], []
    for i, day in enumerate(days):
        if day["precipprob"] < 10:
            cur.append(i)
        else:
            if cur:
                seqs.append(cur)
                cur = []
    if cur:
        seqs.append(cur)

    if not seqs:
        print("\n해당 지역에는 향후 맑은 날이 없습니다!")
        return

    print(f"\n▶ {region} 연속 맑은 날:")
    for seq in seqs:
        ds = today + timedelta(days=seq[0])
        de = today + timedelta(days=seq[-1])
        if len(seq) == 1:
            print(f" • {ds} (단일)")
        else:
            print(f" • {ds} ~ {de} ({len(seq)}일)")

# ——————————————————————————————————————————————
# 메뉴 2-1: 날짜 → 지역 미세먼지 추천
# ——————————————————————————————————————————————
def menu_dust_dates():
    today = datetime.now().date()
    dr = input("\n[2-1] 날짜 입력 (예: 6.10 or 6.10-6.12) ▶ ").strip()
    try:
        if '-' in dr:
            a, b = dr.split('-')
            def to_iso(p):
                m, d = p.split('.')
                return datetime(today.year, int(m), int(d)).date().isoformat()
            dates = [to_iso(a), to_iso(b)]
        else:
            m, d = dr.split('.')
            dates = [datetime(today.year, int(m), int(d)).date().isoformat()]
    except:
        print("형식 오류 – 예시(6.10 or 6.10-6.12)를 참고하세요.")
        return

    scores = {}
    for reg, coord in REGION_COORD.items():
        ap = fetch_air_pollution(*coord)
        vals = [ap[d]["pm2_5"] for d in dates if d in ap]
        if vals:
            scores[reg] = sum(vals) / len(vals)
    if not scores:
        print("\n해당 날짜 예보 데이터가 없습니다!")
        return

    print("\n▶ 지정 날짜 PM2.5 평균 최저 지역 Top3:")
    for i, (r, avg) in enumerate(sorted(scores.items(), key=lambda x: x[1])[:3], 1):
        print(f" {i}. {r}: 평균 PM2.5 {avg:.1f}µg/m³")

# ——————————————————————————————————————————————
# 메뉴 2-2: 지역 → 날짜 미세먼지 추천
# ——————————————————————————————————————————————
def menu_dust_regions():
    user = input("\n[2-2] 지역 입력 ▶ ").strip()
    candidates = [r for r in REGION_COORD if user in r]
    if not candidates:
        print("등록되지 않은 지역입니다!")
        return
    region = candidates[0]
    ap = fetch_air_pollution(*REGION_COORD[region])
    print(f"\n▶ {region} PM2.5 최저 Top3:")
    for date, v in sorted(ap.items(), key=lambda x: x[1]["pm2_5"])[:3]:
        print(f" • {date}: PM2.5 {v['pm2_5']:.1f}µg/m³, PM10 {v['pm10']:.1f}µg/m³")

# ——————————————————————————————————————————————
# 메뉴 3: 여행지 일출·일몰시간 검색
# ——————————————————————————————————————————————
def menu_sun():
    today = datetime.now().date()
    user = input("\n[3] 지역 입력 ▶ ").strip()
    candidates = [r for r in REGIONS if user in r]
    if not candidates:
        print("등록되지 않은 지역입니다!")
        return
    region = candidates[0]
    days = fetch_timeline(region, today.isoformat(), (today + timedelta(days=1)).isoformat())
    print(f"\n▶ {region} 일출·일몰:")
    for i, label in enumerate(["오늘", "내일"]):
        print(f" {label}({days[i]['datetime']}): 일출 {days[i]['sunrise']}, 일몰 {days[i]['sunset']}")

# ——————————————————————————————————————————————
# 메뉴 4: 여행지 맛집 검색
# ——————————————————————————————————————————————
def menu_restaurant():
    q = input("\n[4] 검색어 입력 ▶ ").strip()
    if not q:
        print("검색어를 입력하세요!")
        return
    res = search_blog(q)
    if not res:
        print("검색 결과가 없습니다.")
        return
    print(f"\n▶ '{q}' 맛집 검색 결과:")
    for i, it in enumerate(res, 1):
        print(f"{i}. {it['title']}\n   링크: {it['link']}\n   블로거: {it['blogger']} ({it['date']})\n   요약: {it['desc']}\n")

# ——————————————————————————————————————————————
# 메인 메뉴
# ——————————————————————————————————————————————
def main():
    while True:
        print("\n" + "="*40)
        print("    ✈️  여행 날씨 & 정보 메뉴  ✈️")
        print("="*40)
        print(" 1. 강수량으로 여행 추천")
        print(" 2. 미세먼지로 여행 추천")
        print(" 3. 여행지 일출일몰시간 검색")
        print(" 4. 여행지 맛집 검색")
        print(" 0. 종료")
        print("="*40)
        c = input("메뉴 ▶ ").strip()
        if c == '1':
            print("\n 1) 날짜로 지역 추천   2) 지역으로 날짜 추천")
            s = input("▶ ").strip()
            if s == '1':
                menu_precip_regions()
            elif s == '2':
                menu_precip_dates()
            else:
                print("→ 1 또는 2를 선택해주세요.")
        elif c == '2':
            print("\n 1) 날짜로 지역 추천   2) 지역으로 날짜 추천")
            s = input("▶ ").strip()
            if s == '1':
                menu_dust_dates()
            elif s == '2':
                menu_dust_regions()
            else:
                print("→ 1 또는 2를 선택해주세요.")
        elif c == '3':
            menu_sun()
        elif c == '4':
            menu_restaurant()
        elif c == '0':
            print("\n프로그램을 종료합니다. 감사합니다!")
            break
        else:
            print("→ 1~4 또는 0을 입력해주세요.")

if __name__ == "__main__":
    main()
