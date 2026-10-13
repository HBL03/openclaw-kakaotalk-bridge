# OpenClaw KakaoTalk Bridge

Windows 카카오톡의 **나와의 채팅**에서 OpenClaw에 명령을 보내고, 실행 결과와 정기 알림을 받는 브리지입니다. 기존 OpenClaw Gateway의 에이전트와 모델 설정을 사용합니다.

## 주요 기능

### 카카오톡 명령 및 응답

나와의 채팅에 `!ai`로 시작하는 메시지를 보내면 OpenClaw가 명령을 처리하고 같은 채팅방에 응답합니다. 후속 질문은 동일한 대화 세션에서 이어집니다.

```text
!ai 오늘 할 일을 정리해 줘
!ai 방금 정리한 목록을 우선순위대로 나눠 줘
```

OpenClaw의 응답에는 `[OpenClaw]` 접두어가 붙습니다. 일반 메모와 봇 응답은 새 명령으로 처리하지 않습니다. 사용할 수 있는 도구와 실행 권한은 기존 OpenClaw 설정을 따릅니다.

### 정기 알림 수신

OpenClaw Cron 작업의 실행 결과를 카카오톡으로 전달합니다. 일회성 알림과 반복 일정 모두 OpenClaw에서 관리하며, 알림에는 `[OpenClaw 알림]` 접두어가 붙습니다.

에이전트에 Cron 도구 사용 권한이 있으면 채팅으로 일정 등록을 요청할 수 있습니다.

```text
!ai 매일 오전 9시에 오늘 일정을 정리해서 카카오톡으로 알려 줘
!ai 30분 뒤에 회의 준비하라고 카카오톡으로 알려 줘
```

작업의 전달 설정은 다음과 같습니다. 아래 JSON은 Cron 작업 전체가 아닌 `delivery` 항목입니다.

```json
{
  "mode": "announce",
  "channel": "kakao-local",
  "to": "self"
}
```

일정 등록 여부는 OpenClaw의 작업 목록에서 확인합니다. 브리지에 별도의 스케줄러는 없습니다.

## 구성

```text
카카오톡 나와의 채팅 ↔ Windows 브리지 ↔ OpenClaw Gateway
                                          ├─ 에이전트: 명령 처리와 응답
                                          └─ Cron: 예약 작업과 정기 알림
```

Windows 브리지는 카카오톡 창의 메시지를 읽고 전송합니다. Gateway의 `kakao-local` 채널은 명령을 기존 에이전트로 전달하고, 응답과 알림을 브리지로 보냅니다. 채널과 브리지는 로컬 WebSocket으로 연결합니다.

## 실행 환경

| 구성 요소 | 기준 환경 |
| --- | --- |
| 운영체제 | Windows x64, 로그인된 사용자 세션 |
| 카카오톡 | Windows PC 클라이언트, 나와의 채팅 창 |
| OpenClaw | `2026.10.2`, WSL Gateway |
| Python | `3.11` — 소스 실행 및 빌드 |
| Node.js | `24.19.0` — 채널 실행 및 빌드 |
| Inno Setup | `6` — 설치 EXE 빌드 시 필요 |

설치 도구의 기본 WSL 배포판은 `OpenClawGateway`, Linux 사용자는 `openclaw`입니다. 환경별 검증 결과는 [검증 현황](docs/STATUS.md)에 기록합니다.

## 설치 및 연결

### 한 명령으로 설치

저장소를 내려받은 디렉터리의 Windows PowerShell에서 실행합니다. Python 3.11, Node.js 24.19.0 및 기존 WSL OpenClaw Gateway가 필요합니다.

```powershell
powershell -NoProfile -File .\install.ps1
```

이 명령은 의존성 설치, 채널 빌드·등록, 페어링 및 Gateway 재시작을 수행하고 결과를 JSON 한 건으로 반환합니다. 같은 패키지를 다시 설치하면 기존 키와 설정을 유지합니다. Gateway 재시작을 미루려면 `-NoRestart`를 지정합니다. 설치 후 `.\.venv\Scripts\pythonw.exe -m kakao_local.main`으로 설정 창을 열고 아래 연결 설정의 1·2·4·5단계를 진행합니다. 채널 패키지 설치는 반복할 필요가 없습니다.

Windows 실행 도구를 사용할 수 있는 OpenClaw에는 다음과 같이 요청할 수 있습니다.

> 이 저장소의 INSTALL_AGENT.md에 따라 카카오톡 브리지를 설치하고, JSON 결과의 다음 작업을 알려 줘.

세부 실행 조건과 오류별 조치는 [설치 에이전트 지침](INSTALL_AGENT.md)에 있습니다. Portable 패키지에서도 포함된 `install.ps1`을 사용할 수 있으며 Python과 Node.js의 Windows 빌드 환경은 필요하지 않습니다. 카카오톡 로그인과 본인 채팅방 확인은 사용자가 수행합니다.

### 소스 실행

PowerShell에서 저장소 디렉터리를 열고 실행합니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\apps\windows-bridge[dev]"
npm ci --ignore-scripts
npm run build
.\.venv\Scripts\python.exe -m kakao_local.main
```

### 패키지 빌드

```powershell
# Windows 실행 파일, portable ZIP, 채널 패키지 생성
.\installer\build.ps1 -PortableOnly

# 설치 EXE 추가 생성 — Inno Setup 6 필요
.\installer\build.ps1
```

결과물은 `dist/`에 생성됩니다. 일반 빌드는 서명되지 않습니다. 서명 빌드 절차는 [배포 문서](docs/RELEASE.md)에 설명합니다.

### 연결 설정

1. 카카오톡에 로그인하고 **나와의 채팅** 창을 엽니다.
2. 브리지 설정에 본인 채팅방의 창 제목과 메시지 표시 이름을 입력하고 본인 방 확인란을 선택합니다.
3. **채널 패키지 설치**에서 빌드한 `.tgz` 파일을 선택합니다. 같은 디렉터리에 `.tgz.sha256` 파일이 있어야 합니다.
4. OpenClaw Gateway를 재시작하고 브리지의 **OpenClaw 연결**을 선택합니다.
5. 상태가 **새 명령 대기 중**이면 카카오톡에서 `!ai ping`을 보내 응답을 확인합니다.

카카오톡 읽기·쓰기는 **P0 echo 시작**으로 별도 점검할 수 있습니다. 설치·업데이트·제거 절차는 [설치 문서](docs/INSTALLATION.md)를 참고합니다.

## 토큰 사용량 관리

새 `!ai` 명령만 에이전트에 전달하며 채팅 창 감시, 중복 판별, 설치 상태 확인에는 모델을 호출하지 않습니다. 세션을 유지하고 동일한 프롬프트 캐시 키를 사용합니다. 캐시 적용 여부는 모델 제공자에 따라 달라집니다.

`channels.kakao-local`의 기본 설정은 `dmHistoryLimit: 12`, `maxRequestsPerHour: 60`입니다. 전자는 OpenClaw의 사용자 대화 턴 보존 기준이며, SDK의 일괄 정리 방식에 따라 정리 전 최대 18턴이 유지될 수 있습니다. 후자는 최근 1시간 동안 수락한 명령 수를 제한합니다. 초과한 명령은 모델 호출 없이 거절하며 다음 시간대로 자동 이월하지 않습니다. 중복 전송은 추가 요청으로 계산하지 않습니다.

최종 응답만 카카오톡으로 전달합니다. 이력 제한은 입력 문맥을 줄이는 기능이며 총 토큰이나 요금의 상한은 아닙니다. 모델의 출력 토큰 한도, 도구 결과 크기 및 Cron 실행 비용은 기존 OpenClaw 설정에서 관리합니다. 브리지는 모델 선택이나 도구 권한을 변경하지 않습니다.

## 동작 조건

- 연결 대상은 본인 계정의 **나와의 채팅** 하나입니다. 다른 대화방과 파일·이미지 전송은 지원하지 않습니다.
- 카카오톡 메시지를 읽고 전송하려면 PC와 브리지가 실행 중이어야 합니다. Windows 잠금·절전·로그아웃 중에는 UI 처리가 제한됩니다.
- 기본 감시 주기는 5초이며, 키보드·마우스 입력이 3초 이상 멈춘 경우에 UI를 조작합니다. 이 과정에서 포커스와 클립보드가 일시적으로 바뀔 수 있습니다.
- 브리지 시작 시 이미 존재하는 메시지는 명령으로 재실행하지 않습니다.
- 발송 대기 메시지는 최초 접수 후 15분 이내에만 전달합니다. 전송 여부를 확인할 수 없는 메시지는 자동 재발송하지 않습니다.

## 개발 및 검증

```powershell
# 카카오톡과 모델을 사용하지 않는 모의 왕복 검사
.\.venv\Scripts\python.exe -m kakao_local.main --demo

# 자동 테스트 및 정적 검사
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\ruff.exe check apps/windows-bridge/src tests scripts
npm run typecheck
npm test
```

Node.js가 여러 버전이면 테스트에 사용할 실행 파일을 `KAKAO_TEST_NODE` 환경 변수에 지정합니다.

## 문서

- [설치·업데이트·제거](docs/INSTALLATION.md)
- [사용법 및 문제 해결](docs/USER_GUIDE.md)
- [구조 및 전송 규약](docs/ARCHITECTURE.md)
- [검증 현황](docs/STATUS.md) · [수동 검증 항목](docs/TEST_MATRIX.md)
- [보안 및 데이터 정책](SECURITY.md)
- [구현 계획서](OpenClaw_KakaoTalk_Local_Bridge_Implementation_Plan.md)

## 라이선스

Copyright (c) 2026 Hyeonbeen Lee.

프로젝트 코드는 [MIT License](LICENSE)를 따릅니다. 제3자 구성 요소의 라이선스와 저작권은 [별도 고지](THIRD_PARTY_NOTICES.md)에 명시합니다.
