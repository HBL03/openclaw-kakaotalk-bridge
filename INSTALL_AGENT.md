# OpenClaw 설치 지침

Windows 실행 도구에서 검토한 저장소 또는 portable ZIP을 풀어 놓은 디렉터리를 사용한다. 소스 설치에는 Python 3.11, Node.js 24.19.0과 npm이 필요하다. WSL `OpenClawGateway`의 `openclaw` 사용자가 OpenClaw 2026.10.2를 이미 사용하고 있어야 한다. 새 Gateway 설치와 모델 설정은 이 도구의 범위에 포함하지 않는다.

1. `powershell -NoProfile -File .\install.ps1 -Action Check`로 로컬 전제 조건을 확인한다. 이 명령은 Gateway 연결을 검증하지 않는다.
2. `powershell -NoProfile -File .\install.ps1`로 설치한다. 기존 Gateway를 재시작한다. 재시작을 미루려면 `-NoRestart`를 지정한다.
3. 표준 출력의 JSON 한 건을 읽고 `next`에 따라 안내한다. 전체 빌드 로그, 채팅 기록, 개인 설정이나 페어링 키를 모델 문맥에 넣지 않는다.

| 결과 또는 다음 작업 | 처리 |
| --- | --- |
| `prerequisite_missing` | Windows 도구, Python 3.11, Node.js 24.19.0 및 WSL 설치 경로를 확인한다. `-PythonPath`, `-NodePath`, `-Distro`로 명시할 수 있다. |
| `dependency_install_failed`, `channel_build_failed` | `.cache/install-build.log`의 마지막 오류 부분만 확인한다. |
| `gateway_preflight_failed` | 지정한 WSL 배포판, 사용자, OpenClaw 버전과 JSON 설정을 확인한다. |
| `close_bridge_before_install` | 브리지를 종료한 뒤 다시 설치한다. |
| `wsl_install_failed_review_gateway_plugin_diagnostics` | OpenClaw 플러그인 진단을 확인한다. 기존 수동 설치나 다른 패키지 버전은 자동 덮어쓰지 않는다. |
| `check_gateway` | Gateway 시작 후 `powershell -NoProfile -File .\install.ps1 -Action Doctor`로 재검사한다. |
| `confirm_self_in_settings` | 앱에서 창 제목·본인 표시 이름을 입력하고 나와의 채팅을 확인한 뒤 연결한다. |
| `test_chat` | 사용자가 `!ai ping`을 보내 실제 응답을 확인한다. |

소스 설치 후 설정 앱 실행: `.\.venv\Scripts\pythonw.exe -m kakao_local.main`. Portable 패키지는 `OpenClawKakaoLocal.exe`를 실행한다. 소스 디렉터리는 실행에 필요하므로 유지한다. 같은 패키지를 재설치하면 기존 페어링 키와 설정을 재사용한다.

`Doctor`는 인증된 로컬 연결만 확인하며 카카오톡 창을 읽거나 메시지를 전송하지 않는다. `kakaoVerified:false`는 실제 채팅 검증이 별도로 필요하다는 뜻이다. Windows 실행 도구가 없는 OpenClaw 환경에서는 위 명령을 사용자가 Windows PowerShell에서 실행하도록 안내한다. 설치를 위해 WSL interop 또는 앱 접근 권한을 자동 변경하지 않는다.

관리자 실행은 기본 요구 사항이 아니다. Codex의 Computer Use 카카오톡 승인과 Windows 관리자 권한은 별개이며, 관리자 실행으로 앱별 승인을 대체할 수 없다.
