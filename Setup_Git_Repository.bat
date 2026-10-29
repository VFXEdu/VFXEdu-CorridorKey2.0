@echo off
@chcp 65001 >nul
cd /d "%~dp0"

echo =====================================================================
echo  VFXEdu CorridorKey 2.0 - Git & GitHub Repository Setup Wizard
echo =====================================================================
echo.
echo 이 스크립트는 본 프로젝트를 사용자의 GitHub 레포지토리에 연결하고,
echo 버전 태그(v0.1.3)를 생성하여 푸시할 수 있도록 도와줍니다.
echo.

set /p "GITHUB_URL=내 GitHub 레포지토리 URL (예: https://github.com/사용자명/레포명.git): "
if "%GITHUB_URL%"=="" goto finish

echo.
echo [*] GitHub 원격 저장소(origin) 등록 중...
git remote rename origin upstream 2>nul
git remote remove origin 2>nul
git remote add origin %GITHUB_URL%
git remote -v

echo.
echo [*] 변경 사항 및 새 파일 스테이징 중...
git add .
git commit -m "feat: VFXEdu CorridorKey 2.0 v0.1.3 Desktop Suite Release"

echo.
echo [*] 버전 태그 v0.1.3 생성 중...
git tag -d v0.1.3 2>nul
git tag -a v0.1.3 -m "VFXEdu CorridorKey 2.0 v0.1.3"

echo.
echo =====================================================================
echo 준비가 완료되었습니다! 이제 다음 명령으로 GitHub에 푸시하세요:
echo   git push -u origin master --tags
echo.
echo 푸시 후 GitHub Actions가 자동으로 포터블 ZIP 배포본을 빌드하여
echo GitHub Releases에 등록합니다.
echo =====================================================================
set /p "DO_PUSH=지금 바로 GitHub에 푸시하시겠습니까? [Y/N] (기본값: Y): "
if /i "%DO_PUSH%"=="N" goto finish

git push -u origin master --tags

:finish
echo.
pause
