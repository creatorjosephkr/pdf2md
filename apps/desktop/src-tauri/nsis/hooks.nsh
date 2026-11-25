!macro NSIS_HOOK_POSTINSTALL
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayName" "PDF 얼개"
  IfFileExists "$DESKTOP\${PRODUCTNAME}.lnk" 0 +2
    Delete "$DESKTOP\${PRODUCTNAME}.lnk"
  CreateShortcut "$DESKTOP\PDF 얼개.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
  IfFileExists "$SMPROGRAMS\${PRODUCTNAME}.lnk" 0 +2
    Delete "$SMPROGRAMS\${PRODUCTNAME}.lnk"
  CreateShortcut "$SMPROGRAMS\PDF 얼개.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  Delete "$DESKTOP\PDF 얼개.lnk"
  Delete "$SMPROGRAMS\PDF 얼개.lnk"
!macroend
