# 오라씨오 성가대 1주년 인기 특송 Top 10

지난 1년 동안 가장 많이 들은 특송 Top 10을 1위부터 소개하는 정적 웹페이지입니다.
GitHub Pages로 서빙합니다.

## 공개 주소

https://atinjin.github.io/atinjin-pages/oratio/

## 구성

- `oratio/index.html` — 페이지 전체 (HTML · CSS · JS가 한 파일에 담겨 있음). `/oratio/` 경로로 서빙됩니다.
- `.github/workflows/pages.yml` — `main` 브랜치에 push되면 GitHub Pages로 자동 배포
- `.nojekyll` — Jekyll 처리 없이 파일을 그대로 서빙

## GitHub Pages 켜는 법 (최초 1회)

이 브랜치를 `main`에 병합한 뒤, 저장소에서:

1. **Settings → Pages** 로 이동
2. **Build and deployment → Source** 를 **GitHub Actions** 로 설정

이후 `main`에 push할 때마다 워크플로가 자동으로 배포합니다.

## 순위표 수정

`oratio/index.html` 안의 `SONGS` 배열만 고치면 순위표가 바뀝니다.
`views` 칸에 조회수를, `date` 칸에 업로드 날짜를 적으면 카드에 함께 표시됩니다.
(예: `views:"1,234회", date:"2025. 8. 3"`)

엠블럼은 `oratio/emblem.png`, 채널 통계(특송·구독자 수)는 `index.html` 머리말의
`.stats` 영역에서 고칠 수 있습니다.

본문·제목 글꼴은 **가톨릭체**(`oratio/catholic.woff2`, 구형 브라우저용 `catholic.ttf`)를
`@font-face`로 불러와 씁니다. 숫자와 일부 라틴 문구는 Cormorant Garamond를 씁니다.
