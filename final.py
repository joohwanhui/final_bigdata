import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
import urllib.request
import urllib.parse
import json
import re
import sys
from datetime import datetime, timedelta
from collections import defaultdict

# —————————————————————————————————————————————————————————
# 경고 메시지 억제 (XML을 HTML 파서로 읽을 때 발생하는 경고 무시)
# —————————————————————————————————————————————————————————
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# —————————————————————————————————————————————————————————
# 1) KMA 격자 좌표 매핑 (예시)
# —————————————————————————————————————————————————————————
REGION_GRID = {
    '서울':    (60, 127),
    '인천':    (55, 124),
    '수원':    (60, 120),
    '부산':    (97, 74),
    '대구':    (89, 90),
    '광주':    (58, 74),
    '울산':    (102, 84),
    '제주':    (52, 38),
    # 필요시 더 추가...
}

# —————————————————————————————————————————————————————————
# 2) 네이버 블로그 API 정보 (본인의 클라이언트 정보로 교체)
# —————————————————————————————————————————————————————————
NAVER_CLIENT_ID     = "jh4j9OLJJV71zlU6TiBn"
NAVER_CLIENT_SECRET = "3uNogYwcqj"

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)

def search_blog(query):
    enc = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/blog?query={enc}&display=5"
    req = urllib.request.Request(url)
    req.add_header("X-Naver-Client-Id", NAVER_CLIENT_ID)
    req.add_header("X-Naver-Client-Secret", NAVER_CLIENT_SECRET)
    try:
        res = urllib.request.urlopen(req)
        if res.getcode() == 200:
            data = json.loads(res.read().decode())
            items = data.get("items", [])
            return [{
                "title":       clean_html(item.get("title","")),
                "link":        item.get("link",""),
                "description": clean_html(item.get("description","")),
                "blogger":     item.get("bloggername",""),
                "date":        item.get("postdate","")
            } for item in items]
    except Exception as e:
        print("API 호출 중 예외 발생:", e)
    return []

# —————————————————————————————————————————————————————————
# 3) 기상청 일별 최대 강수확률 가져오기
# —————————————————————————————————————————————————————————
def fetch_daily_max_pop(gridx, gridy):
    url = "https://www.kma.go.kr/wid/queryDFS.jsp"
    r = requests.get(url, params={"gridx":gridx, "gridy":gridy})
    r.encoding = 'utf-8'
    soup = BeautifulSoup(r.text, 'html.parser')
    data_nodes = soup.find_all('data')
    pops = defaultdict(int)
    for node in data_nodes:
        d = int(node.find('day').text)
        p = int(node.find('pop').text)
        if 0 <= d < 7:
            pops[d] = max(pops[d], p)
    return {i: pops.get(i,0) for i in range(7)}

def find_clear_sequences(max_pops):
    seqs, cur = [], []
    for i in range(7):
        if max_pops[i] < 10:
            cur.append(i)
        else:
            if cur:
                seqs.append(cur); cur=[]
    if cur: seqs.append(cur)
    return seqs

# —————————————————————————————————————————————————————————
# 메뉴 1: 여행가기 좋은 날 추천
# —————————————————————————————————————————————————————————
def menu_recommend_dates_for_region():
    region = input("\n[1] 가고 싶은 지역 ▶ ").strip()
    if region not in REGION_GRID:
        print("등록되지 않은 지역입니다.")
        sys.exit(0)
    gx, gy = REGION_GRID[region]
    pops = fetch_daily_max_pop(gx, gy)
    seqs = find_clear_sequences(pops)
    today = datetime.now().date()
    if not seqs:
        print("맑은 연속 구간이 없습니다.")
    else:
        print(f"\n🎉 {region} 지역 연속 맑은 날:")
        for seq in seqs:
            s, e = seq[0], seq[-1]
            ds = today + timedelta(days=s)
            de = today + timedelta(days=e)
            if s==e:
                print(f" • {ds} (단일 맑음)")
            else:
                print(f" • {ds} ~ {de} (연속 {len(seq)}일)")
    sys.exit(0)

# —————————————————————————————————————————————————————————
# 메뉴 2: 여행가기 좋은 지역 추천
# —————————————————————————————————————————————————————————
def menu_recommend_region_for_dates():
    print("\n[2] 날짜 입력 예: 6.10-6.12")
    dr = input("기간 ▶ ").strip()
    try:
        a,b = dr.split('-')
        am,ad=a.split('.'); bm,bd=b.split('.')
        y = datetime.now().year
        d0 = (datetime(y,int(am),int(ad)).date() - datetime.now().date()).days
        d1 = (datetime(y,int(bm),int(bd)).date() - datetime.now().date()).days
    except:
        print("형식 오류")
        sys.exit(0)
    offs = [d for d in range(d0,d1+1) if 0<=d<7]
    if not offs:
        print("예보 범위 벗어남")
        sys.exit(0)
    best, mx = [], -1
    for reg,(gx,gy) in REGION_GRID.items():
        pops = fetch_daily_max_pop(gx,gy)
        cnt = sum(1 for d in offs if pops[d]<10)
        if cnt>mx:
            mx, best=[reg], cnt
        elif cnt==mx:
            best.append(reg)
    if mx<=0:
        print("맑은 날 없음")
    else:
        print(f"\n🎉 최다 맑음({mx}일):")
        for r in best[:3]:
            print(f" • {r}")
    sys.exit(0)

# —————————————————————————————————————————————————————————
# 메뉴 3: 맛집 검색
# —————————————————————————————————————————————————————————
def menu_restaurant_search():
    query = input("\n[3] 검색어 (ex : ooo맛집,ooo밥집,ooo한식 등..) ▶ ").strip()
    if not query:
        print("검색어를 입력해야 합니다.")
        sys.exit(0)
    res = search_blog(query)
    if not res:
        print("검색 결과가 없습니다.")
    else:
        print(f"\n🍽️ '{query}' 검색 결과:")
        for i,item in enumerate(res,1):
            print(f"{i}. {item['title']}")
            print(f"   링크   : {item['link']}")
            print(f"   블로거 : {item['blogger']} ({item['date']})")
            print(f"   요약   : {item['description']}\n")
    sys.exit(0)

# —————————————————————————————————————————————————————————
# 메인 메뉴
# —————————————————————————————————————————————————————————
def main_menu():
    while True:
        print("\n==============================")
        print("   ✈️  여행 & 맛집 메뉴")
        print("==============================")
        print(" 1. 여행가기 좋은 날 추천")
        print(" 2. 여행가기 좋은 지역 추천")
        print(" 3. 맛집 검색")
        print(" 0. 종료")
        print("==============================")
        c = input("번호 ▶ ").strip()
        if c=='1':
            menu_recommend_dates_for_region()
        elif c=='2':
            menu_recommend_region_for_dates()
        elif c=='3':
            menu_restaurant_search()
        elif c=='0':
            print("종료합니다.")
            break
        else:
            print("1~3 또는 0을 입력해주세요.")

if __name__ == "__main__":
    main_menu()
