# blogBot — 쉽게 따라 하는 생활 디지털

50~60대 독자(와 부모님 폰을 대신 설정해 드리는 자녀)를 위한 생활 디지털 블로그 제작 레포입니다.

## 역할 나누기

| 단계 | 담당 | 하는 일 | 결과물 |
|---|---|---|---|
| 1. 원고 | Claude | 주제 조사, 메뉴 경로 확인, 원고와 그림 요청서 작성 | `posts/<글>/post.md`, `images.yaml` |
| 2. 그림 | GPT | `images.yaml`을 읽고 그림 생성 | `posts/<글>/images/01.png` … |
| 3. 확인 | 사람 | 내 폰으로 메뉴 이름이 맞는지 확인, 체크리스트 체크 | `post.md` 상단 `checked: true` |
| 4. 완성본 | 빌드 스크립트 | 원고 + 그림을 합쳐 복사용 페이지 생성 | `dist/<글>/index.html` |

## 폴더 구조

```
posts/
  2026-11-galaxy-text-size/
    post.md          ← 원고 (Claude)
    images.yaml      ← 그림 요청서 (Claude)
    images/          ← 그림 (GPT)
dist/
  2026-11-galaxy-text-size/
    index.html       ← 복사용 완성본 (빌드 결과)
    post.txt         ← 텍스트만
    gpt_prompt.md    ← GPT에 그대로 붙여 넣을 그림 요청문
docs/
  writing-guide.md   ← 원고 작성 규칙
  image-guide.md     ← 그림 공통 스타일
scripts/build.py     ← 완성본 빌드
AGENTS.md            ← GPT(그림 담당) 작업 규칙
STATUS.md            ← 글별 진행 현황
```

## 완성본 만들기

```bash
pip install -r requirements.txt
python scripts/build.py              # 모든 글
python scripts/build.py 2026-11-galaxy-text-size   # 특정 글
```

`dist/<글>/index.html`을 브라우저로 열면 다음 버튼이 있습니다.

- **제목 복사** / **태그 복사**
- **본문 서식 복사**: 제목·굵게·번호 목록이 유지된 채 복사됩니다. 그림 자리는 `[그림 1]`처럼 표시됩니다.
- **본문 텍스트만 복사**
- **그림 내려받기**: 번호 순서대로 저장해서 `[그림 N]` 자리에 넣으면 됩니다.

그림이 아직 없으면 회색 "그림 대기" 상자가 대신 들어갑니다.

## GPT에게 그림 맡기기

1. `dist/<글>/gpt_prompt.md` 내용을 ChatGPT에 붙여 넣습니다. (레포 접근이 되는 GPT라면 `AGENTS.md`를 읽으라고만 해도 됩니다.)
2. 받은 그림을 `posts/<글>/images/` 에 요청서의 파일 이름(`01.png` 등) 그대로 올립니다.
3. 빌드를 다시 돌리면 완성본에 그림이 들어갑니다. (GitHub에 올리면 Actions가 자동으로 빌드합니다.)

실제 폰 화면을 캡처해서 쓰고 싶은 그림은 같은 파일 이름으로 덮어쓰면 됩니다. 화면 안내 그림은 캡처가 가장 정확합니다.
