# 구조와 상태 계약

`apps/windows-bridge`는 Python/PySide6 사용자 세션 앱입니다. Win32 어댑터, 스냅샷 파서,
SQLite 발송 저널, P0 echo, 트레이와 WSL 설치 보조 기능을 포함합니다.
`packages/openclaw-kakao-channel`은 OpenClaw SDK 기반 TypeScript 플러그인입니다.
기존 에이전트 라우팅을 유지하고 세션 키 `agent:<agentId>:kakao-local:default:direct:self`를 씁니다.
MCP 도구만 등록하는 방식이나 별도 모델 API 호출은 사용하지 않습니다.

## 관찰과 중복

클립보드 원문을 날짜·시간·발신자·전체 본문으로 파싱합니다. 첫 관찰과 재시작/재연결/잠금 복귀 시
관찰은 기준선입니다. 기존 대화를 재실행하지 않습니다. 이후 스냅샷의 순서와 전체 해시를 비교합니다.
동일 내용이 뒤에 추가되면 별도 이벤트 UUID를 발급합니다. 오래된 앞부분이 사라졌을 때는 두 메시지
이상의 유일한 겹침만 허용합니다. 겹침이 모호하면 중단합니다.

스냅샷이 완전히 같으면 새 메시지 여부를 증명할 수 없습니다. 클라이언트가 같은 내용만으로 이루어진
고정 길이 창을 제공하면 누락될 수 있습니다. 수동 메시지 본문이 카카오톡 복사 형식의 헤더를 흉내
내는 경우에도 경계 판정 한계가 있습니다. 봇 출력의 헤더처럼 보이는 줄은 U+2060으로 escape합니다.
원본 계획의 단순 내용 해시 비교보다 개선했지만 고유 메시지 ID를 대체하지는 않습니다.

## 전달과 큐

| 경계 | 보장 |
| --- | --- |
| 관찰 → Windows 저널 | 신규 이벤트 ID, 입력 4,000자, 대기 최대 5개 |
| Windows → 채널 | 인증 후 저장하고 ACK, 동일 ID·본문 재수신 시 에이전트 재실행 방지 |
| 채널 → 에이전트 | 동시 1개, 처리 중 재시작은 `unknown`, 모델 실행 자동 재시도 없음 |
| SDK → 채널 | SDK durable queue ID와 part index를 그대로 사용, 발송 큐 최대 10개 |
| 채널 → Windows | 원래 ID·본문·만료를 유지, 살아 있는 SDK 호출이 소유한 요청만 재연결 전달 |
| Windows → UI | `sending`을 먼저 기록, 발송 후 새 스냅샷 증거로 `confirmed` 또는 `unknown` |

출력은 16,000자까지, 실제 메시지는 접두어 포함 1,000자 이하입니다. 한 발송의 일부만 확인된
상태에서 실패하면 전체를 `unknown`으로 남기고 다음 부분을 보내지 않습니다. `unknown`은
자동 재발송하지 않습니다. UI 확인은 카카오 서버/휴대폰 배달 영수증이 아닙니다. SDK에 가짜
provider ID를 반환하지 않으므로 호스트의 identity 없는 receipt 분류도 실제 E2E 검증 대상입니다.

15분 TTL은 채널이 outbound 요청을 처음 받은 시점부터 계산합니다. 재시도·재연결로 연장하지
않습니다. PC 전원이 꺼져 Cron 자체가 실행되지 않은 기간을 재생성하는 정책은 OpenClaw 소관입니다.
이미 발송 시도된 요청의 만료는 `unknown`, 아직 보내지 않은 요청은 `expired`입니다.

## IPC v1

[JSON Schema](../contracts/bridge-v1.schema.json)와 양쪽 `protocol` 모듈이 계약입니다.
한 WebSocket 메시지가 UTF-8 JSON 프레임 하나이며 최대 65,536 bytes입니다. 시각은 Unix
epoch milliseconds입니다. 연결 후 3초 안에 `hello`를 보내고 `ready`를 기다립니다. 인증된
연결은 한 개만 허용합니다. Ping/Pong으로 단절을 감지합니다.

| type | 방향 | 주요 필드 |
| --- | --- | --- |
| `hello` | Windows → 채널 | `v`, `bridgeId`, `token` |
| `ready` | 채널 → Windows | `v` |
| `inbound.message` | Windows → 채널 | `eventId`, `roomId: self`, `observedAt`, `text` |
| `outbound.message` | 채널 → Windows | `deliveryId`, `roomId: self`, `createdAt`, `expiresAt`, `kind`, `text` |
| `ack` | 양방향 | `id`, `status` |
| `cancel.delivery` | 채널 → Windows | `id` |

추가 필드는 향후 확장을 위해 무시합니다. 버전 변경, 잘못된 ID, 다른 방, 빈 본문/NUL,
유효하지 않은 시각·만료는 거부합니다. Schema 외에도 TTL 차이가 `0 < TTL <= 900000`인지
런타임에서 검사합니다. 취소는 큐 대기 항목만 중단할 수 있으며 진행 중 UI 전송을 되돌리지 못합니다.

SDK 참고: [채널 플러그인](https://docs.openclaw.ai/plugins/sdk-channel-plugins),
[outbound 계약](https://docs.openclaw.ai/plugins/sdk-channel-outbound),
[Cron announce](https://docs.openclaw.ai/automation/cron-jobs/delivery).
