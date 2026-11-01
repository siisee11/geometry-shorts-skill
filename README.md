# geometry-shorts-skill

위성 지도 위에 나라·왕조 영토를 국기 무늬 입체 판으로 세우고, 카메라가 날아다니며 순위나 시대 변화를 보여 주는 세로 지도 쇼츠(1080×1920)를 만드는 Agent skill입니다.

## 사용법: 에이전트에게 말하기

Codex, Claude, Grok 같은 코딩 에이전트에게 이렇게 말하면 됩니다. 설치는 필요 없습니다.

> https://github.com/siisee11/geometry-shorts-skill 을 이용해서 **아프리카에서 가장 큰 나라 TOP5** 영상 만들어줘

> https://github.com/siisee11/geometry-shorts-skill 을 이용해서 **유럽연합이 커진 과정**을 연대기 영상으로 만들어줘

에이전트가 이 저장소를 받아 주제를 조사하고, 영상 설정(`show.json`)을 쓰고, 스틸로 확인한 뒤 `video.mp4`를 만들어 줍니다. 코드를 실행할 수 있는 에이전트(Codex CLI·앱, Claude Code, Grok Build 등)여야 하고, 필요한 것은 Python 3.10 이상과 인터넷뿐입니다. 30초 영상 하나에 보통 10~20분 걸립니다(처음엔 지도 데이터 받기 포함).

- **등수 형식**: "○○에서 가장 큰 나라 TOP N"처럼 제목 → 카운트다운, 지도 아래 "N. 이름"과 올라가는 숫자
- **연대기 형식**: "○○의 역사", "○○ 제국의 확장"처럼 시대마다 영토가 바뀌고, 지도 위에 이름과 연도

## For AI agents

You were given this repository and asked to make a map video. Do this:

1. **Get the code.** `git clone --depth 1 https://github.com/siisee11/geometry-shorts-skill` (if git is missing, download `https://github.com/siisee11/geometry-shorts-skill/archive/refs/heads/main.zip`). Work in a folder of your own, e.g. `episodes/<slug>/` next to the clone.
2. **Read `SKILL.md` and follow it.** It is the full procedure: decide the entries and their sourced numbers, find territories, write `episodes/<slug>/show.json`, check the plan and stills, render, deliver. It is written in Korean; reply to the user in their language. The `show.json` format is in `references/show-json.md`; start from `assets/examples/sea-top5/show.json` (ranking) or `assets/examples/eu-timeline/show.json` (timeline).
3. **Run everything through one script** (needs only Python 3.10+; the first run installs its packages and an ffmpeg into `~/.cache/map-shorts/venv`, about a minute):
   ```bash
   RUN="python3 geometry-shorts-skill/scripts/run.py"
   $RUN countries france vietnam                   # Natural Earth code ("iso"), flag code ("cdn"), area
   $RUN episodes/<slug> --plan                     # order, values, camera, map area (seconds)
   $RUN episodes/<slug> --still 4.6,7.9            # stills -> episodes/<slug>/out/stills/ ; open and look at them
   $RUN episodes/<slug> --fps 30 > episodes/<slug>/out/render.log 2>&1 &   # the video, in the background
   $RUN episodes/<slug> --status                   # poll until "finished: .../out/video.mp4"
   ```
   The first still of a new region downloads NASA map tiles (~70 MB each) and can take several minutes: give it a long timeout. A full render is a few minutes on 8+ cores; `--fps 30` halves it.
4. **Deliver** `episodes/<slug>/out/video.mp4` (attach it if you can) and tell the user where each number came from and which borders are approximate.

If your environment cannot run Python or reach the internet (for example a chat app without code execution), say so and give the user the `show.json` you would use plus these commands, instead of pretending to render.

## 직접 설치해서 쓰기 (선택)

에이전트가 매번 저장소를 받지 않고 스킬로 바로 알아보게 하려면 설치합니다.

```bash
git clone https://github.com/siisee11/geometry-shorts-skill && cd geometry-shorts-skill
./install.sh            # Claude Code(~/.claude/skills)와 Codex·Grok Build 등(~/.agents/skills)에 한 번에
```

| 에이전트 | 설치 위치 | 명령 |
|---|---|---|
| Claude Code | `~/.claude/skills/map-shorts` | `./install.sh claude` |
| Codex (최신) | `~/.agents/skills/map-shorts` | `./install.sh agents` |
| Grok Build (xAI CLI) | `~/.agents/skills/map-shorts` 또는 `~/.grok/skills/map-shorts` | `./install.sh agents` 또는 `./install.sh grok` |
| Codex (예전 버전) | `~/.codex/skills/map-shorts` | `./install.sh codex-old` |
| 한 프로젝트에만 | `<폴더>/.claude/skills`, `<폴더>/.agents/skills` | `./install.sh --project <폴더>` |

Grok 웹앱·Grok Bot처럼 파일을 가져오는 곳에는 [릴리스](https://github.com/siisee11/geometry-shorts-skill/releases)의 `map-shorts.zip`을 쓸 수 있습니다. 다만 영상은 파이썬을 실행할 수 있어야 만들어집니다.

## 직접 실행

```bash
RUN="python3 geometry-shorts-skill/scripts/run.py"
mkdir -p episodes/sea-top5 && cp geometry-shorts-skill/assets/examples/sea-top5/show.json episodes/sea-top5/
$RUN episodes/sea-top5 --plan        # 순위·값·카메라 확인
$RUN episodes/sea-top5 --still 5,8   # 스틸 → episodes/sea-top5/out/stills/
$RUN episodes/sea-top5               # 음악까지 들어간 영상 → episodes/sea-top5/out/video.mp4
```

## 구성

| 경로 | 내용 |
|---|---|
| `SKILL.md` | 스킬 본문(모든 에이전트 공통): 형식 고르기, 절차, 공개할 때 주의할 점 |
| `references/` | show.json 전체 형식 |
| `assets/examples/` | 동남아시아 면적 TOP5(등수), 유럽연합의 확장(연대기) |
| `scripts/` | `run.py`(입구)와 렌더러·도구 (numpy + Pillow + shapely, 블렌더 불필요) |
| `AGENTS.md` | 이 폴더에서 에이전트를 열었을 때 읽는 안내 |
| `install.sh` | 에이전트별 스킬 폴더에 설치 |
| `evals/` | 스킬 테스트 케이스 3개 (`claude plugin eval` 형식) |

카메라 움직임, 와이프 전환, 글자 위치, 색감은 기본값이 정해져 있어서 따로 정하지 않아도 지도 쇼츠다운 리듬으로 나옵니다.

## 데이터와 라이선스

- 코드: MIT ([LICENSE](LICENSE))
- 위성 지도: [NASA Blue Marble Next Generation](https://visibleearth.nasa.gov/collection/1484/blue-marble) w/ Topography and Bathymetry (퍼블릭 도메인)
- 국경·해안선: [Natural Earth](https://www.naturalearthdata.com/) 1:10m (퍼블릭 도메인). 실효 지배 기준이라 분쟁 지역(예: 크림반도)은 필요하면 직접 고쳐야 합니다.
- 국기 그림: [flagcdn.com](https://flagcdn.com/) (퍼블릭 도메인 국기 이미지, 나라별 사용 규정은 따로 확인)
- 글꼴: [Pretendard](https://github.com/orioncactus/pretendard), [Noto Serif KR](https://fonts.google.com/noto/specimen/Noto+Serif+KR) (SIL OFL, 처음 쓸 때 받음)
- 음악: 코드로 합성 (샘플 없음)

영상 설명란 표기 예: "Map imagery: NASA Blue Marble Next Generation. Boundaries: Natural Earth."
