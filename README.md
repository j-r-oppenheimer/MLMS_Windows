# MLMS Windows — 충남대 의대 LMS 데스크톱 위젯

충남대 의대 LMS(cnu.u-lms.com)의 시간표를 바탕화면에 표시하는 비공식 Windows 데스크톱 위젯

[안드로이드 버전](https://github.com/j-r-oppenheimer/MLMS)을 바탕으로 만든 Windows 데스크톱 앱입니다.

## 다운로드

[Releases](https://github.com/j-r-oppenheimer/MLMS_Windows/releases)에서 `MLMS.exe`를 다운로드하여 실행하면 됩니다. 별도 설치 불필요.

## 기능

- 바탕화면 시간표 위젯 (주별 탐색, A/B반 필터)
- 시험 일정 하이라이트
- 수업 블록 클릭 시 상세 정보 (과목, 교수, 시간, 강의실)
- 수업 자료 다운로드
- 자동 로그인
- 다크 모드 / 투명도 / 폰트 등 커스터마이징
- 시스템 트레이 상주

## 스크린샷

<img width="730" height="897" alt="스크린샷 2026-03-05 233348" src="https://github.com/user-attachments/assets/acc2a76d-3473-4f0b-bdbe-8fc624d3ddf0" />

## 빌드

```bash
build.bat
```

의존성 설치와 PyInstaller 빌드를 한 번에 하며, `dist/MLMS.exe`가 생성됩니다. 앱 아이콘(`mlms.ico`, `mlms_tray.ico`)이 같은 폴더에 있어야 합니다.

## 사용 기술

Python · PyQt6 · QWebEngine
