# blogBot — 쉽게 따라 하는 생활 디지털

50~60대 독자(와 부모님 폰을 대신 설정해 드리는 자녀)를 위한 생활 디지털 블로그 제작 레포입니다.

## 역할 나누기

| 단계 | 담당 | 하는 일 | 결과물 |
|---|---|---|---|
| 1. 원고 | Claude | 주제 조사, 메뉴 경로 확인, 원고와 그림 요청서 작성 | `posts/<글>/post.md`, `images.yaml` |
| 2. 그림 | GPT | `images.yaml`에서 `photo`가 아닌 항목만 그림 생성 | `posts/<글>/images/01.png` … |
| 2-1. 실사 사진 | Claude + Actions | 무료 사진 사이트(Pexels 등)에서 후보 선정 → Actions가 내려받음 → 보고 고름(`pick`) | `posts/<글>/photos/photo-01-1.jpg` … |
| 3. 확인 | 사람 | 내 폰으로 메뉴 이름이 맞는지 확인, 체크리스트 체크 | `post.md` 상단 `checked: true` |
| 4. 완성본 | 빌드 스크립트 | 원고 + 그림을 합쳐 복사용 페이지 생성 | `dist/<글>/index.html` |

## 폴더 구조

```
posts/
  2026-11-galaxy-text-size/
    post.md          ← 원고 (Claude)
    images.yaml      ← 그림 요청서 (Claude)
    images/          ← 그림 (GPT), 직접 찍은 캡처
    photos/          ← 실사 사진 후보 (Actions가 내려받음)
dist/
  2026-11-galaxy-text-size/
    index.html       ← 복사용 완성본 (빌드 결과)
    post.txt         ← 텍스트만
    gpt_prompt.md    ← GPT에 그대로 붙여 넣을 그림 요청문
docs/
  writing-guide.md   ← 원고 작성 규칙
  image-guide.md     ← 그림 공통 스타일
scripts/build.py     ← 완성본 빌드
scripts/fetch_photos.py ← 실사 사진 후보 내려받기 (Actions에서 실행)
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

1. 완성본 페이지의 **GPT 요청 문구 복사** 버튼을 누르거나 `dist/<글>/gpt_request.txt` 내용을 복사해 ChatGPT에 붙여 넣습니다.
   - 요청 문구 안에 상세 요청서(`gpt_prompt.md`) 공개 주소가 들어 있어 GPT가 직접 읽습니다.
   - 이미 올라온 그림은 목록에서 자동으로 빠집니다.
2. GPT가 한 장씩 만들면 받은 그림을 요청서의 파일 이름(`01.png` 등)으로 저장합니다. 그림 속 글자가 틀렸으면 다시 만들어 달라고 합니다.
3. GitHub 웹에서 `posts/<글>/images/` 폴더 → **Add file → Upload files**로 올립니다.
4. 올리면 Actions가 자동으로 완성본을 다시 만듭니다(1분 정도).

## 실사 사진

- `images.yaml`에서 `type: photo` 항목이 실사 사진 칸입니다. GPT는 건드리지 않습니다.
- `candidates`에 적힌 후보를 GitHub Actions가 `posts/<글>/photos/`에 내려받습니다. (작업 환경에서는 사진 사이트에 접속이 안 돼서 Actions가 받습니다.)
- 마음에 드는 후보 번호를 `pick`에 적으면 완성본에 들어갑니다. 비어 있으면 1번이 임시로 들어가고, 완성본 맨 위에 후보 사진이 모두 보입니다.
- 출처는 사진 설명 뒤에 `(사진: 작가 / Pexels)`로 자동으로 붙습니다.
- 다른 사진을 쓰고 싶으면 `images/photo-01.jpg`처럼 같은 이름으로 올리면 그 파일이 우선합니다.

실제 폰 화면을 캡처해서 쓰고 싶은 그림은 같은 파일 이름으로 덮어쓰면 됩니다. 화면 안내 그림은 캡처가 가장 정확합니다.
