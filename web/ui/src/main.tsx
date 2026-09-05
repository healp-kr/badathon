/* 진입점 — 로드 순서가 곧 의존 순서였던 바닐라 버전과 달리,
 * 여기서는 import 그래프가 의존을 표현한다. 새 파일을 index.html 에 등록할 일이 없다.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import 'leaflet/dist/leaflet.css';
import './styles/tokens.css';
import './styles/base.css';
import './styles/controls.css';

import { AppProvider } from './state/AppContext';
import App from './App';

const host = document.getElementById('root');
if (!host) throw new Error('#root 를 찾지 못했습니다');

createRoot(host).render(
  <StrictMode>
    <AppProvider>
      <App />
    </AppProvider>
  </StrictMode>,
);
