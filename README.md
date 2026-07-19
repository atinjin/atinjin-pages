# 오라씨오 성가대 1주년 인기 특송

지난 1년 동안 가장 많이 들은 특송 열 곡을 1위부터 소개하는 정적 웹페이지입니다.
GitHub Pages로 서빙합니다.

## 공개 주소

https://atinjin.github.io/atinjin-pages/

## 구성

- `index.html` — 페이지 전체 (HTML · CSS · JS가 한 파일에 담겨 있음)
- `.github/workflows/pages.yml` — `main` 브랜치에 push되면 GitHub Pages로 자동 배포
- `.nojekyll` — Jekyll 처리 없이 파일을 그대로 서빙

## GitHub Pages 켜는 법 (최초 1회)

이 브랜치를 `main`에 병합한 뒤, 저장소에서:

1. **Settings → Pages** 로 이동
2. **Build and deployment → Source** 를 **GitHub Actions** 로 설정

이후 `main`에 push할 때마다 워크플로가 자동으로 배포합니다.

## 순위표 수정

`index.html` 안의 `SONGS` 배열만 고치면 순위표가 바뀝니다.
`views` 칸에 조회수를 적으면 이름 옆에 함께 표시됩니다. (예: `views:"1.2만 회"`)
