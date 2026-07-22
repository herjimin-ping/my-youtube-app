"""
유튜브 댓글 AI 요약 앱 - 1단계
------------------------------------------------
- 유튜브 영상 링크를 입력받아 댓글을 최대 100개까지 가져오고
- Solar API(모델: solar-open2)로 댓글 전체를 한국어 세 줄로 요약해주는 스트림릿 앱입니다.

[secrets.toml 예시] (스트림릿 클라우드 > Settings > Secrets 에 아래처럼 넣어주세요)
YOUTUBE_API_KEY = "여기에_유튜브_API_키"
SOLAR_API_KEY = "여기에_솔라_API_키"
"""

import re
from urllib.parse import urlparse, parse_qs

import requests
import streamlit as st
from openai import OpenAI


# ----------------------------------------
# 기본 설정값
# ----------------------------------------
# 기본 예시 링크 (딥마인드 다큐, 영어 댓글)
DEFAULT_URL = "https://youtu.be/d95J8yzvjbQ?si=LfL5DLwCL8Pk077r"
# 두번째 예시 링크 (2002 월드컵 추억, 한국어 댓글)
EXAMPLE2_URL = "https://youtu.be/I9vK5EVTt0U?si=NEZ8L7MRuNvrzINa"

st.set_page_config(page_title="유튜브 댓글 AI 요약", page_icon="💬", layout="centered")
st.title("💬 유튜브 댓글 AI 요약 (1단계)")
st.caption("유튜브 영상 링크를 넣으면 댓글을 모아서 보여주고, AI가 한국어로 세 줄 요약을 해줍니다.")


# ----------------------------------------
# 함수: 유튜브 링크에서 영상 ID 뽑아내기
# ----------------------------------------
def extract_video_id(url: str):
    """
    유튜브 링크(짧은 주소 youtu.be, 일반 주소 youtube.com/watch)에서
    영상 ID만 뽑아내는 함수입니다.
    링크 뒤에 붙는 si= 같은 추가 값은 무시합니다.
    """
    if not url:
        return None

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None

    host = (parsed.hostname or "").lower()

    # 1) youtu.be/영상ID  형태 (짧은 링크)
    if host in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.lstrip("/")
        return video_id if video_id else None

    # 2) youtube.com/watch?v=영상ID  형태
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            query = parse_qs(parsed.query)
            video_id = query.get("v", [None])[0]
            return video_id
        # youtube.com/embed/영상ID  형태도 혹시 몰라 함께 처리
        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/embed/")[-1]

    return None


# ----------------------------------------
# 함수: 유튜브 댓글 가져오기 (YouTube Data API v3)
# ----------------------------------------
def fetch_comments(video_id: str, api_key: str):
    """
    commentThreads API를 호출해서 댓글을 최대 100개 가져옵니다.
    - part=snippet
    - order=relevance (좋아요 많은 순 = 인기순)
    """
    endpoint = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "order": "relevance",   # 최신순이 아니라 인기(관련도)순
        "maxResults": 100,
        "textFormat": "plainText",
        "key": api_key,
    }

    response = requests.get(endpoint, params=params, timeout=15)
    response.raise_for_status()  # 에러가 있으면 여기서 예외 발생
    data = response.json()

    comments = []
    for item in data.get("items", []):
        top_snippet = item["snippet"]["topLevelComment"]["snippet"]
        text = top_snippet.get("textOriginal", "")
        like_count = top_snippet.get("likeCount", 0)
        comments.append({"댓글": text, "좋아요": like_count})

    return comments


# ----------------------------------------
# 함수: Solar API로 댓글 세 줄 요약하기
# ----------------------------------------
def summarize_comments(comments: list, api_key: str):
    """
    댓글 전체를 Solar API(solar-open2 모델)에 보내서
    한국어 세 줄 요약 + 긍정/부정 비율 추정을 받아옵니다.
    """
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.upstage.ai/v1",
    )

    # 댓글들을 하나의 텍스트로 합치기 (좋아요 수도 참고용으로 같이 전달)
    comments_text = "\n".join(
        f"- (좋아요 {c['좋아요']}개) {c['댓글']}" for c in comments
    )

    system_prompt = (
        "너는 유튜브 댓글 반응을 분석하는 어시스턴트야. "
        "주어진 댓글들을 읽고 시청자들의 전체 반응을 한국어로 정확히 세 줄로 요약해. "
        "마지막 줄에는 댓글 내용을 바탕으로 추정한 긍정 반응과 부정 반응의 대략적인 비율을(백분율, 예: 긍정 70% / 부정 30%) 반드시 덧붙여."
    )
    user_prompt = f"다음은 한 유튜브 영상의 댓글 목록이야:\n\n{comments_text}"

    completion = client.chat.completions.create(
        model="solar-open2",
        reasoning_effort="none",  # 추론(생각) 기능 끄기
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    return completion.choices[0].message.content


# ----------------------------------------
# 세션 상태 초기화 (입력창 값, 댓글 목록 저장용)
# ----------------------------------------
if "youtube_url" not in st.session_state:
    st.session_state.youtube_url = DEFAULT_URL

if "comments" not in st.session_state:
    st.session_state.comments = None


# ----------------------------------------
# 예시 버튼 두 개 (입력창 위, 나란히 배치)
# ----------------------------------------
col1, col2 = st.columns(2)

with col1:
    if st.button("예시 1 · 딥마인드 다큐(영어 댓글)", use_container_width=True):
        st.session_state.youtube_url = DEFAULT_URL
        st.session_state.comments = None  # 링크가 바뀌면 이전 댓글 결과는 초기화

with col2:
    if st.button("예시 2 · 2002 월드컵 추억(한국어 댓글)", use_container_width=True):
        st.session_state.youtube_url = EXAMPLE2_URL
        st.session_state.comments = None


# ----------------------------------------
# 유튜브 링크 입력창
# ----------------------------------------
url_input = st.text_input("유튜브 영상 링크를 붙여넣어 주세요", key="youtube_url")


# ----------------------------------------
# 댓글 가져오기 버튼
# ----------------------------------------
if st.button("📥 댓글 가져오기", type="primary"):
    video_id = extract_video_id(url_input)

    if not video_id:
        st.error("링크에서 영상 ID를 찾지 못했어요. 유튜브 링크 형식이 맞는지 확인해 주세요. 😥")
    else:
        try:
            youtube_api_key = st.secrets["YOUTUBE_API_KEY"]
        except Exception:
            st.error("YOUTUBE_API_KEY가 설정되어 있지 않아요. 스트림릿 클라우드의 Secrets 설정을 확인해 주세요. 🔑")
        else:
            with st.spinner("댓글을 가져오는 중이에요..."):
                try:
                    comments = fetch_comments(video_id, youtube_api_key)

                    if not comments:
                        st.warning("이 영상에는 가져올 수 있는 댓글이 없어요. 댓글이 꺼져 있거나 아직 없는 영상일 수 있어요. 🙏")
                        st.session_state.comments = None
                    else:
                        # 좋아요 많은 순으로 정렬해서 세션에 저장
                        comments_sorted = sorted(comments, key=lambda c: c["좋아요"], reverse=True)
                        st.session_state.comments = comments_sorted
                        st.success(f"댓글 {len(comments_sorted)}개를 가져왔어요! 👍")

                except requests.exceptions.HTTPError as e:
                    st.error(
                        "유튜브 댓글을 가져오는 중 오류가 발생했어요. "
                        "API 키가 올바른지, 댓글이 허용된 영상인지 확인해 주세요. 😥\n\n"
                        f"(자세한 오류: {e})"
                    )
                    st.session_state.comments = None
                except Exception as e:
                    st.error(f"알 수 없는 오류로 댓글을 가져오지 못했어요. 잠시 후 다시 시도해 주세요. 😥\n\n(자세한 오류: {e})")
                    st.session_state.comments = None


# ----------------------------------------
# 댓글 결과 보여주기 (지표 카드 + 표)
# ----------------------------------------
if st.session_state.comments:
    comments = st.session_state.comments

    st.metric(label="가져온 댓글 개수", value=f"{len(comments)}개")

    st.dataframe(
        comments,
        use_container_width=True,
        column_config={
            "댓글": st.column_config.TextColumn("댓글", width="large"),
            "좋아요": st.column_config.NumberColumn("좋아요 수"),
        },
        hide_index=True,
    )

    st.divider()

    # ----------------------------------------
    # AI 세 줄 요약 버튼
    # ----------------------------------------
    if st.button("✨ AI 세 줄 요약"):
        try:
            solar_api_key = st.secrets["SOLAR_API_KEY"]
        except Exception:
            st.error("SOLAR_API_KEY가 설정되어 있지 않아요. 스트림릿 클라우드의 Secrets 설정을 확인해 주세요. 🔑")
        else:
            with st.spinner("AI가 댓글을 읽고 요약하는 중이에요..."):
                try:
                    summary = summarize_comments(comments, solar_api_key)
                    st.subheader("📝 AI 세 줄 요약")
                    st.write(summary)
                except Exception as e:
                    st.error(f"AI 요약에 실패했어요. 잠시 후 다시 시도해 주세요. 😥\n\n(자세한 오류: {e})")
