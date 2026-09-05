import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/* 개발 중에는 Vite 가 5173 에서 화면을 내고, /api 는 FastAPI(8000)로 넘긴다.
 *
 *   터미널 1  python -m uvicorn web.main:app --port 8000
 *   터미널 2  cd web/ui && npm run dev
 *
 * 시연·배포는 빌드본 하나로 끝난다. `npm run build` 결과(dist/)를 `web/main.py` 가
 * 루트에 마운트하므로 8000 하나만 띄우면 된다.
 *
 * 번들은 CDN 을 타지 않는다 — "시연장 네트워크를 믿지 않는다" 는 원칙 그대로다.
 * Leaflet 도 vendor/ 수동 복사 대신 npm 의존성으로 번들에 들어간다.
 */
export default defineConfig({
  /* GitHub Pages 는 `<아이디>.github.io/<저장소>/` 아래에 얹힌다. 절대 경로(`/assets/...`)
   * 로 빌드하면 저장소 이름이 박혀서, 이름을 바꾸는 순간 화면이 깨진다.
   * 상대 경로로 두면 어느 경로에 올려도 그대로 뜬다 — 로컬 `dist/` 를 파일로 열어도 된다.
   * 이 앱은 클라이언트 라우팅이 없어(탭이 상태로만 바뀐다) URL 이 항상 루트에 머물므로
   * 상대 경로가 어긋날 자리가 없다. */
  base: './',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    // 시연 중 원인을 되짚을 수 있어야 한다. 번들 크기보다 중요하다.
    sourcemap: true,
  },
});
