# 공개 배포 조건

개발 빌드와 공개 베타는 구분합니다. 현재 버전은 `dev`이므로 공개 빌드는 항상 실패합니다.
CI의 개발 artifact도 서명된 릴리스가 아닙니다. 자동 업로드/게시 작업은 없습니다.

1. 지원 버전에서 [수동 검증표](TEST_MATRIX.md)를 실제로 통과합니다. UI 읽기/쓰기가 안 되면 P0
   no-go이며, 본인 방 판별 조건을 느슨하게 만들어 통과시키지 않습니다.
2. 버전을 공개 베타 버전으로 변경합니다. 루트 npm·채널 npm·Python 버전과 lockfile을 맞춥니다.
3. 해당 소스 commit과 14일 이내 검증 날짜를 포함한 evidence JSON을 작성합니다. 테스트 이후 코드가
   바뀌면 다시 검증합니다. 개인 대화·토큰은 넣지 않습니다.
4. Qt/PySide의 정확한 corresponding source, 라이선스/고지 제공을 검토합니다.
5. 코드 서명 인증서가 있는 Windows 빌드 환경에서 실행합니다:

```powershell
.\installer\build.ps1 -PublicRelease -Evidence release-evidence.local.json -CertificateThumbprint YOUR_CERTIFICATE_THUMBPRINT
```

스크립트는 깨끗한 Git tree, source commit, 실제 검증 결과, 공개 버전, 서명을 요구합니다.
서명 도구 `signtool.exe`와 Inno Setup 6는 사전에 설치되어야 합니다. 인증서 개인 키는 저장소나
빌드 결과에 넣지 않습니다. 생성된 EXE와 설치 EXE의 Authenticode 상태가 Valid인지 검사하며
SHA256SUMS를 만듭니다. ZIP 안의 실행 파일도 서명합니다.

공개 빌드에서는 Inno Setup에 같은 서명 도구를 지정해 제거 파일도 서명합니다.
SmartScreen 평판과 새 PC에서의 신뢰 체인 검증은 별도 배포 운영 검토에 포함합니다.
개발 CI는 공개 릴리스를 생성하지 않습니다. 이 게이트는 사람이 기록한 증거의 완전성 검사이며
카카오톡 실제 동작이나 진술의 진위를 자동으로 증명하지 않습니다.

원샷 프롬프트는 위 절차를 통과한 버전·설치 경로·서명 정보를 안내할 수 있을 때 README에 추가합니다.
로그인·본인 방 확인·권한 동의는 원샷 자동화에서도 사용자가 수행합니다.
