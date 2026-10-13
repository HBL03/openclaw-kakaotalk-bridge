# OpenClaw KakaoTalk Local Bridge

Windows 카카오톡 **나와의 채팅**을 기존 OpenClaw 에이전트에 연결하는 로컬 브리지입니다.
채널 ID는 `kakao-local`, 유일한 발송 대상은 `self`입니다.

**현재 상태: 개발 미리보기 `0.1.0-dev.1`.** 통신·상태 관리·SDK 연결 코드와 모의 통합 테스트를
구현했습니다. 실제 카카오톡에서의 읽기/쓰기, 모델 왕복, Cron 알림, 서명된 설치 파일은
검증 전입니다. 공개 베타나 원샷 설치가 준비된 상태로 안내하지 않습니다.
[검증 현황](docs/STATUS.md)과 [출시 조건](docs/RELEASE.md)을 먼저 확인하세요.

```text
카카오톡 나와의 채팅 → Windows 브리지 → loopback WebSocket → OpenClaw 채널
       ↑                                                   ↓
       └──────────── 응답 / Cron announce ← 기존 에이전트 ─┘
```

- `!ai 질문`만 새 명령으로 전달합니다. 개인 메모와 봇 출력은 전달하지 않습니다.
- 기존 에이전트·모델·도구 권한을 사용하며, 전용 세션에서 대화를 이어갑니다.
- 응답은 `[OpenClaw]`, 알림은 `[OpenClaw 알림]`으로 시작합니다. 긴 출력은 1,000자 이하로 나눕니다.
- 입력이 3초 이상 멈춘 경우에만 UI를 조작합니다. 기본 감시 주기는 5초입니다.
- 로컬 큐에 처음 들어온 발송은 15분 이내에만 전달합니다. 불확실한 발송은 자동 재발송하지 않습니다.
- 카카오 계정 비밀번호, 카카오 내부 DB, 비공식 로그인/네트워크 프로토콜은 사용하지 않습니다.

## 개발 환경

검증 대상으로 고정한 환경은 Windows x64, Python 3.11, Node 24.19.0,
OpenClaw `2026.10.2`, PySide6 `6.8.3`입니다. 다른 SDK 버전은 자동으로 호환된다고 가정하지 않습니다.
기존 OpenClaw Gateway는 WSL 배포판 `OpenClawGateway`의 `openclaw` 사용자로 실행되어야 합니다.

PowerShell에서:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\apps\windows-bridge[dev]"
npm ci --ignore-scripts
npm run build
.\.venv\Scripts\python.exe -m kakao_local.main --demo
```

`--demo`는 메모리 어댑터로만 동작하며 카카오톡이나 모델을 호출하지 않습니다.
설정 창은 `python -m kakao_local.main`으로 실행합니다. 실제 P0 echo는 사용자가 본인 방을
확인한 뒤 직접 시작하는 별도 테스트입니다. 시작할 때 존재한 대화는 기준선으로만 사용합니다.

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\ruff.exe check apps/windows-bridge/src tests scripts
npm run typecheck
npm test
```

Node가 여러 버전이면 Node 24 실행 파일을 `KAKAO_TEST_NODE`에 지정할 수 있습니다.
실제 Python ↔ TypeScript WebSocket 왕복 테스트도 위 테스트에 포함됩니다.

## 빌드와 설치

```powershell
# 개발용 portable ZIP + 채널 .tgz + SHA256
.\installer\build.ps1 -PortableOnly

# Inno Setup 6가 설치된 경우 개발용 설치 EXE도 생성
.\installer\build.ps1
```

결과물은 `dist/`에 생성됩니다. 개발 빌드는 서명되지 않으며 공개 배포 대상이 아닙니다.
빌드 스크립트는 기존 Gateway 설정을 변경하지 않습니다. 채널 설치는 설정 창에서 `.tgz`와
함께 생성된 `.tgz.sha256`을 선택해 명시적으로 실행합니다.

[설치·업데이트·제거](docs/INSTALLATION.md) · [사용·문제 해결](docs/USER_GUIDE.md) ·
[구조·전송 규약](docs/ARCHITECTURE.md) · [수동 검증표](docs/TEST_MATRIX.md) ·
[보안·데이터 정책](SECURITY.md)

## 범위와 제약

개인 계정 비공식 UI 자동화입니다. 다른 사람과의 대화, 단체방, 파일/이미지, 대량 발송은 지원하지
않습니다. 포커스와 클립보드가 잠시 바뀔 수 있으며 PC 잠금·절전·로그아웃 중 동작은 보장하지 않습니다.
창 제목만으로 본인 방을 판정하지 않으므로, 현재 클라이언트가 방 유형 증거를 제공하지 않으면
`self_room_type_unverified`로 중단합니다. 이 조건을 완화해 우회하지 않습니다.

카카오톡의 고유 메시지 ID를 얻을 수 없어 **정확히 한 번 배달을 보장하지 않습니다**.
로컬 UI 확인과 휴대폰 수신 확인은 다릅니다. 모호한 경우 재시도보다 누락을 선택합니다.
클립보드에서 구분할 수 없는 동일 스냅샷이나 메시지 경계를 흉내 낸 수동 붙여넣기도 한계입니다.

구현 기준: [원본 계획서](OpenClaw_KakaoTalk_Local_Bridge_Implementation_Plan.md).
프로젝트 코드는 [MIT](LICENSE), 제3자 구성 요소는 [별도 고지](THIRD_PARTY_NOTICES.md)를 따릅니다.
