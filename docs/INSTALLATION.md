# 설치, 업데이트, 제거

현재는 개발자 검증용입니다. 서명된 공개 설치 파일과 검증된 원샷 설치 프롬프트는 아직 없습니다.
Windows x64 일반 사용자 세션, Python 3.11(소스 실행만), Node 24.19.0(빌드만),
OpenClaw `2026.10.2`가 필요합니다. 카카오톡 로그인과 나와의 채팅 창 열기는 사용자가 직접 합니다.

## Windows 앱

1. README의 개발 환경 명령으로 의존성과 채널을 빌드합니다.
2. `installer/build.ps1 -PortableOnly`로 생성한 ZIP을 개인 폴더에 풉니다.
3. `OpenClawKakaoLocal.exe`를 실행합니다. 처음에는 감시가 꺼져 있습니다.
4. 본인 채팅방의 정확한 창 제목과 복사된 메시지에 나오는 본인 표시 이름을 입력합니다.
5. 본인 방 확인란을 선택하고 저장합니다. 로그인 시 자동 시작은 별도로 선택해야 활성화됩니다.
6. [P0 수동 검증](TEST_MATRIX.md)을 진행합니다. 확인하지 못한 방에는 전송하지 않습니다.

Inno Setup 6가 있으면 `installer/build.ps1`로 사용자 전용 설치 EXE도 빌드합니다. 설치는 관리자
권한을 요구하지 않으며 `%LOCALAPPDATA%\Programs\OpenClawKakaoLocal`을 기본으로 사용합니다.

## 기존 WSL Gateway에 채널 추가

기본 대상은 `OpenClawGateway`, Linux 사용자는 `openclaw`입니다. 기존 Gateway가 정상 동작하는지
Companion에서 먼저 확인합니다. 브리지는 모델·에이전트·Gateway 인증 설정을 만들거나 바꾸지 않습니다.

1. 개발 빌드의 채널 `.tgz`와 `.tgz.sha256`을 같은 폴더에 둡니다. 같은 출처의 해시는 무결성 확인이며
   발행자 인증이 아니므로 배포자·서명 확인을 대신하지 않습니다.
2. Windows 설정 창에서 **채널 패키지 설치**를 눌러 tarball을 선택합니다.
3. 설치기는 WSL에 stdin으로 패키지를 전달하고 해시와 OpenClaw 버전을 확인합니다. Windows 드라이브
   마운트나 interop 활성화는 필요하지 않습니다.
4. `~/.openclaw/kakao-local/config.before-install.json`에 원본 설정을 `0600`으로 백업하고
   `openclaw plugins install`을 실행합니다. `channels.kakao-local`, 해당 plugin entry와 allow 항목만
   추가합니다. 플러그인 설치에 대한 OpenClaw 자체 검사가 거부하면 그 정책을 우회하지 않습니다.
5. 성공 후 Companion에서 Gateway를 재시작하고 Windows 앱의 **OpenClaw 연결**을 누릅니다.

설정 파일이 JSON5인 경우 이 설치기는 수정 전에 중단합니다. 자동 설치 대상은 JSON입니다.
이미 채널이 있거나 이전 설치 백업이 있으면 재설치하지 않습니다. 설치가 중간에 실패하면 원본 백업과
현재 상태를 비교해야 합니다. 플러그인 CLI가 완료한 변경은 남을 수 있습니다. 앱이 직접 쓴 설정은
그 뒤 변경이 없을 때만 되돌리며, 다른 작업의 최신 설정을 덮어쓰지 않습니다. 백업 전체를 무조건
복원하면 다른 변경을 잃을 수 있습니다.

`ws://127.0.0.1:29531`만 허용합니다. WSL localhost forwarding 환경에서 실제 연결을 검증해야 하며,
연결 실패를 해결하려고 바인딩을 `0.0.0.0` 또는 LAN IP로 바꾸지 마세요.

## 업데이트와 제거

업데이트는 수동입니다. 트레이에서 중지·종료하고 이전 버전과 설정을 백업한 뒤 검증된 새 빌드를
설치합니다. SDK 버전 고정을 먼저 확인합니다. 기존 채널 업그레이드는 OpenClaw의 플러그인 관리
절차로 수행하며 Windows의 최초 설치 버튼을 반복 사용하지 않습니다.

Windows 설치 버전은 설정 앱의 **설치된 앱**에서 제거합니다. 자동 시작 등록은 삭제하고 데이터는
기본적으로 보존합니다. 제거 중 데이터 삭제를 선택하면 `%LOCALAPPDATA%\OpenClawKakaoLocal`의
설정·키·대기 큐·진단 기록도 삭제합니다. portable 버전은 앱에서 자동 시작을 끈 뒤 종료하고 압축을
푼 폴더를 지웁니다. 개인 데이터 삭제가 필요하면 위 데이터 폴더만 별도로 지웁니다.

WSL 플러그인은 Windows 제거와 별개입니다. Gateway에서 해당 채널을 비활성화하고 재시작한 뒤
`openclaw plugins uninstall kakao-local`의 안내를 확인하세요. 제거 후 `channels.kakao-local`과
해당 entry/allow 잔여 항목, `~/.openclaw/kakao-local`만 정리합니다. 다른 에이전트, API 키,
플러그인과 `~/.openclaw` 전체를 삭제하지 않습니다.
