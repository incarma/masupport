# django_ma Manual App 운영 지침서 (FINAL)

## 1. 개요

-   목적: 매뉴얼(Manual/Section/Block/Attachment) 관리
-   권한: superuser 중심 편집, 일반 사용자는 조회
-   보안: 파일 직접 URL 금지, 반드시 View 경유 다운로드

## 2. 데이터 구조

-   Manual
-   ManualSection (sort_order)
-   ManualBlock (content, image, sort_order)
-   ManualBlockAttachment (file, original_name, size)

## 3. 핵심 보안 정책

-   /media 직접 접근 차단 (NGINX 403)
-   다운로드는 View + 권한검증 + FileResponse
-   업로드: 확장자/MIME/용량 검증
-   HTML: sanitize_quill_html 적용
-   Audit: 모든 주요 액션 log_action 기록

## 4. 주요 API

-   manual_section_add/update/delete/reorder
-   manual_block create/update/delete/reorder/move
-   manual_block_attachment upload/delete/download
-   manual_block_image (inline)

## 5. 프론트 구조

-   Boot: #manualDetailBoot dataset
-   JS: manual_detail_block/\*
-   공통: ManualShared (fetch/csrf/utils)
-   Sortable: section/block drag

## 6. 파일 처리

-   attachment_download → RFC5987 filename
-   image → inline + cache-control

## 7. 운영 커맨드

-   sanitize_manual_blocks \[--apply\]
-   cleanup_manual_files \[--apply --delete-missing-attachments\]

## 8. Audit 정책

-   action / user / object / meta 최소화 저장
-   meta는 mask 처리

## 9. 배포 체크

-   collectstatic
-   nginx /media 차단
-   static 캐시 정책 확인

## 10. 상태

-   보안 패치 완료
-   sanitize/cleanup 정상
-   audit 구조 완료

작성일: 2026-04-27
