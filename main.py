import streamlit as st
import requests
from urllib.parse import urlparse, parse_qs

# ------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------
st.set_page_config(page_title="유튜브 댓글 분석기", page_icon="💬", layout="centered")

# 예시로 쓸 링크 두 개를 미리 정의해둡니다.
EXAMPLE_1_URL = "https://youtu.be/d95J8yzvjbQ?si=LfL5DLwCL8Pk077r"
EXAMPLE_2_URL = "https://youtu.be/I9vK5EVTt0U?si=NEZ8L7MRuNvrzINa"

# 입력창의 값을 앱이 기억하고 있어야 "예시 버튼"을 눌렀을 때
# 입력창 내용을 바꿔줄 수 있습니다. 그래서 session_state를 사용합니다.
if "video_url" not in st.session_state:
    st.session_state.video_url = EXAMPLE_1_URL


def set_example_1():
    """예시 1 버튼을 누르면 입력창을 딥마인드 다큐 링크로 채웁니다."""
    st.session_state.video_url = EXAMPLE_1_URL


def set_example_2():
    """예시 2 버튼을 누르면 입력창을 2002 월드컵 영상 링크로 채웁니다."""
    st.session_state.video_url = EXAMPLE_2_URL


# ------------------------------------------------------------
# 화면 제목
# ------------------------------------------------------------
st.title("💬 유튜브 댓글 분석기 (1단계)")
st.write("유튜브 영상 링크를 입력하면 좋아요가 많은 순서로 댓글을 가져와서 보여줍니다.")

# ------------------------------------------------------------
# 예시 버튼 두 개를 나란히 배치
# ------------------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    st.button("예시 1 · 딥마인드 다큐(영어 댓글)", on_click=set_example_1, use_container_width=True)
with col2:
    st.button("예시 2 · 2002 월드컵 추억(한국어 댓글)", on_click=set_example_2, use_container_width=True)

# ------------------------------------------------------------
# 유튜브 링크 입력창
# ------------------------------------------------------------
video_url = st.text_input("유튜브 영상 링크", key="video_url")

analyze_clicked = st.button("댓글 분석하기", type="primary")


# ------------------------------------------------------------
# 링크에서 영상 ID를 뽑아내는 함수
# ------------------------------------------------------------
def extract_video_id(url: str):
    """
    유튜브 링크에서 영상 ID만 뽑아냅니다.
    - https://youtu.be/영상ID?si=... 형태
    - https://www.youtube.com/watch?v=영상ID&... 형태
    둘 다 처리하고, si= 같은 뒤에 붙는 부가 값은 무시합니다.
    """
    if not url:
        return None

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None

    host = (parsed.hostname or "").lower()

    # 1) youtu.be/영상ID 형태 (짧은 링크)
    if host in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.lstrip("/")
        # 혹시 뒤에 경로가 더 붙어있으면 첫 부분만 사용
        video_id = video_id.split("/")[0]
        return video_id if video_id else None

    # 2) youtube.com/watch?v=영상ID 형태
    if host in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        query = parse_qs(parsed.query)
        if "v" in query and query["v"]:
            return query["v"][0]

    return None


# ------------------------------------------------------------
# YouTube Data API로 댓글을 가져오는 함수
# ------------------------------------------------------------
def fetch_comments(video_id: str, api_key: str):
    """
    commentThreads API를 호출해서 댓글을 최대 100개 가져옵니다.
    성공하면 (댓글 리스트, None)을,
    실패하면 (None, 오류메시지)를 돌려줍니다.
    """
    endpoint = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": 100,
        "order": "relevance",  # 최신순이 아니라 좋아요(관련도) 많은 순
        "key": api_key,
    }

    try:
        response = requests.get(endpoint, params=params, timeout=10)
    except requests.exceptions.RequestException:
        return None, "네트워크 연결에 문제가 있어서 댓글을 가져오지 못했어요."

    data = response.json()

    # API가 오류를 돌려준 경우 (잘못된 영상ID, 댓글 사용 중지 등)
    if response.status_code != 200:
        error_reason = ""
        try:
            error_reason = data["error"]["errors"][0]["reason"]
        except (KeyError, IndexError):
            pass

        if error_reason == "commentsDisabled":
            return None, "이 영상은 댓글 기능이 꺼져 있어서 댓글을 가져올 수 없어요."
        elif error_reason == "videoNotFound":
            return None, "영상을 찾을 수 없어요. 링크가 올바른지 다시 확인해 주세요."
        elif error_reason in ("quotaExceeded", "dailyLimitExceeded"):
            return None, "오늘의 API 사용량을 모두 써버렸어요. 내일 다시 시도해 주세요."
        else:
            return None, "댓글을 가져오는 중 문제가 발생했어요. 링크를 다시 확인해 주세요."

    items = data.get("items", [])
    if not items:
        return None, "가져올 수 있는 댓글이 없어요."

    comments = []
    for item in items:
        try:
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            comments.append(
                {
                    "댓글": snippet.get("textOriginal", ""),
                    "좋아요": snippet.get("likeCount", 0),
                }
            )
        except KeyError:
            continue

    return comments, None


# ------------------------------------------------------------
# 버튼을 누르면 실제로 분석을 실행
# ------------------------------------------------------------
if analyze_clicked:
    video_id = extract_video_id(video_url)

    if not video_id:
        st.error("링크에서 영상 ID를 찾지 못했어요. 유튜브 링크가 맞는지 확인해 주세요.")
    else:
        # secrets 금고에서 API 키 불러오기
        api_key = st.secrets.get("YOUTUBE_API_KEY")

        if not api_key:
            st.error("YOUTUBE_API_KEY가 설정되어 있지 않아요. 스트림릿 클라우드의 Secrets에 등록해 주세요.")
        else:
            with st.spinner("댓글을 가져오는 중이에요..."):
                comments, error_message = fetch_comments(video_id, api_key)

            if error_message:
                st.warning(error_message)
            else:
                # 좋아요 많은 순으로 다시 한 번 정렬
                comments_sorted = sorted(comments, key=lambda c: c["좋아요"], reverse=True)

                # 가져온 댓글 개수를 큰 지표 카드로 표시
                st.metric("가져온 댓글 개수", f"{len(comments_sorted)}개")

                # 댓글 목록을 표로 표시
                st.dataframe(comments_sorted, use_container_width=True)
