# 수동 검증 기록

공개 배포 전에 허용된 개인 테스트 환경에서 수행합니다. 대화 원문·토큰·개인 창 제목은 기록하지 않습니다.
아래 결과는 현재 **전부 미검증**입니다. 자동 테스트 통과를 수동 테스트 결과로 옮기지 마세요.

| 검증 | 절차 / 합격 조건 | evidence 키 |
| --- | --- | --- |
| P0 echo | 앱 시작 후 `!ai ping` 20회, 각각 새 UI 응답 확인 | `p0EchoCount >= 20` |
| 반복 명령 | 같은 분/같은 내용 포함 100개 신규 명령, 모두 각각 한 번 처리 | `commandCount >= 100` |
| 방 보호 | 일반 1:1/단체/제목 같은 창을 선택해도 전송 거부 | `wrongRoomSends == 0`, `selfRoomGuard` |
| 중복 | ACK 유실·재연결·Enter 직후 강제 종료, 중복 발송 0 | `duplicateSends == 0`, `crashRecovery` |
| 클립보드 | 텍스트 복구, 이미지/OLE 대기, 외부 변경 보존 | `clipboardRestored` |
| 포커스 | 다른 앱 사용 중 대기, 자동 동작 중 사용자 전환 시 중단 | `focusGuard` |
| 잠금/재로그인 | 잠금 중 조작 0, 해제/재로그인 뒤 과거 명령 재실행 0 | `lockGuard`, `resumeBaseline` |
| 최소화 | 복구 동작과 포커스 복귀를 측정, 실패 시 명확하게 중단 | `minimizedWindow` |
| 모델·세션 | 기존 에이전트 응답, 후속 질문의 세션 유지 | `agentRoundtrip`, `sessionContinuity` |
| Cron | announce channel/to 명시한 단발 알림 1회 | `cronAnnounce` |
| SDK receipt | native ID 없는 UI 증거가 호스트에서 무한 재시도로 이어지지 않음 | `sdkReceiptSemantics` |
| 오프라인 TTL | 15분 이내 재연결 전달, 15분 초과 전달 0 | `offlineTtl` |
| WSL 연결 | 실제 Windows → WSL 127.0.0.1 연결 및 Gateway 재시작 | `wslLoopback`, `gatewayRestart` |
| 긴 답변 | 모든 부분 접두어/1,000자, 부분 실패 후 자동 재발송 0 | `longReply` |
| 설치/제거 | 깨끗한 사용자 계정에서 설치·업데이트·제거, 기존 모델 설정 유지 | `cleanInstall`, `upgrade`, `uninstall`, `existingConfigPreserved` |

기록에는 실제 source commit, 검증 날짜(UTC), Windows build, 카카오톡/OpenClaw 버전,
테스터 식별자와 민감정보 없는 재현 메모가 필요합니다.
`release/evidence.example.json`을 복사해 `release-evidence.local.json`에 기록하고
`python scripts/check_release.py --evidence release-evidence.local.json`으로 검사합니다.
증거가 없거나 현재 커밋과 다르면 공개 빌드가 실패해야 정상입니다.
